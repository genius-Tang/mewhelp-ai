from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from app.core.messages import to_langchain_messages, trim_history
from app.core.prompts import (
    build_final_answer_prompt_messages,
    build_tool_selector_prompt_messages,
)
from app.db.repository import Repository, TurnBusy
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


class ConversationNotFound(LookupError):
    """Raised when a conversation is missing or belongs to another user."""


class MultipleToolCalls(RuntimeError):
    """Raised when the selector violates the one-tool protocol."""


class EmptyModelResponse(RuntimeError):
    """Raised when the finalizer completes without any text."""


@dataclass(frozen=True, slots=True)
class ToolEvent:
    name: str
    status: Literal["running"] = "running"


@dataclass(frozen=True, slots=True)
class TokenEvent:
    content: str


@dataclass(frozen=True, slots=True)
class DoneEvent:
    conversation_id: int
    tools: tuple[str, ...]


ChatEvent: TypeAlias = ToolEvent | TokenEvent | DoneEvent


class ChatOrchestrator:
    def __init__(
        self,
        *,
        repository: Repository,
        registry: ToolRegistry,
        executor: ToolExecutor,
        model: Any,
        history_max_tokens: int,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._executor = executor
        self._model = model
        self._history_max_tokens = history_max_tokens

    async def stream_turn(
        self,
        user_id: str,
        message: str,
        conversation_id: int | None,
    ) -> AsyncIterator[ChatEvent]:
        conversation = await self._resolve_conversation(user_id, conversation_id)
        async with self._repository.turn_slot(conversation.id):
            await self._repository.append_message(conversation.id, "user", message)

            replay = await self._repository.list_replay_messages(conversation.id)
            history = trim_history(
                to_langchain_messages(replay),
                max_tokens=self._history_max_tokens,
            )
            selector_messages = build_tool_selector_prompt_messages(history)
            selector = self._model.bind_tools(
                self._registry.model_tools,
                tool_choice="auto",
                parallel_tool_calls=False,
            )
            selection = await selector.ainvoke(selector_messages)
            tool_calls = selection.tool_calls
            if len(tool_calls) > 1:
                raise MultipleToolCalls("selector returned more than one tool call")

            selected_tools: tuple[str, ...] = ()
            finalizer_messages = build_final_answer_prompt_messages(history)
            if tool_calls:
                tool_call = self._normalize_tool_call(tool_calls[0])
                await self._repository.append_message(
                    conversation.id,
                    "assistant",
                    None,
                    tool_calls=[tool_call],
                )
                selected_tools = (tool_call["name"],)
                yield ToolEvent(name=tool_call["name"])

                execution = await self._executor.execute(tool_call, conversation.id)
                await self._repository.append_message(
                    conversation.id,
                    "tool",
                    execution.message.text,
                    tool_call_id=execution.message.tool_call_id,
                )
                finalizer_messages.extend([selection, execution.message])

            answer_parts: list[str] = []
            async for chunk in self._model.astream(finalizer_messages):
                text = chunk.text
                if text:
                    answer_parts.append(text)
                    yield TokenEvent(content=text)

            answer = "".join(answer_parts)
            if not answer:
                raise EmptyModelResponse("finalizer returned no text")

            await self._repository.append_message(
                conversation.id,
                "assistant",
                answer,
            )
        yield DoneEvent(conversation_id=conversation.id, tools=selected_tools)

    async def _resolve_conversation(
        self, user_id: str, conversation_id: int | None
    ) -> Any:
        if conversation_id is None:
            return await self._repository.create_conversation(user_id)
        conversation = await self._repository.get_conversation(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFound("conversation does not exist")
        return conversation

    @staticmethod
    def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": tool_call.get("id", ""),
            "name": tool_call.get("name", ""),
            "args": tool_call.get("args", {}),
        }
