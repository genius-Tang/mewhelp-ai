from types import SimpleNamespace

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.services.chat import (
    ChatOrchestrator,
    ConversationNotFound,
    DoneEvent,
    EmptyModelResponse,
    MultipleToolCalls,
    TokenEvent,
    ToolEvent,
)
from app.tools.executor import ToolExecution


class FakeRepository:
    def __init__(self) -> None:
        self.conversations: dict[int, str] = {}
        self.messages: list[SimpleNamespace] = []
        self.next_conversation_id = 1

    async def create_conversation(self, user_id: str) -> SimpleNamespace:
        conversation = SimpleNamespace(id=self.next_conversation_id, user_id=user_id)
        self.conversations[conversation.id] = user_id
        self.next_conversation_id += 1
        return conversation

    async def get_conversation(
        self, conversation_id: int, user_id: str
    ) -> SimpleNamespace | None:
        if self.conversations.get(conversation_id) != user_id:
            return None
        return SimpleNamespace(id=conversation_id, user_id=user_id)

    async def append_message(
        self,
        conversation_id: int,
        role: str,
        content: str | None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> SimpleNamespace:
        message = SimpleNamespace(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        self.messages.append(message)
        return message

    async def list_replay_messages(
        self, conversation_id: int
    ) -> list[SimpleNamespace]:
        return [
            message
            for message in self.messages
            if message.conversation_id == conversation_id
            and (
                message.role == "user"
                or (
                    message.role == "assistant"
                    and message.content
                    and message.tool_calls is None
                )
            )
        ]


class FakeBoundSelector:
    def __init__(self, reply: AIMessage) -> None:
        self.reply = reply
        self.calls: list[list] = []

    async def ainvoke(self, messages: list) -> AIMessage:
        self.calls.append(messages)
        return self.reply


class FakeChatModel:
    def __init__(
        self,
        selector_reply: AIMessage,
        chunks: list[str],
        *,
        stream_error: Exception | None = None,
    ) -> None:
        self.selector = FakeBoundSelector(selector_reply)
        self.chunks = chunks
        self.stream_error = stream_error
        self.bind_calls: list[tuple[list, dict]] = []
        self.astream_calls: list[list] = []

    def bind_tools(self, tools: list, **kwargs) -> FakeBoundSelector:
        self.bind_calls.append((tools, kwargs))
        return self.selector

    async def astream(self, messages: list):
        self.astream_calls.append(messages)
        for content in self.chunks:
            yield AIMessageChunk(content=content)
        if self.stream_error is not None:
            raise self.stream_error


class FakeRegistry:
    def __init__(self) -> None:
        self.model_tools = [
            SimpleNamespace(name="query_order"),
            SimpleNamespace(name="query_product"),
            SimpleNamespace(name="query_logistics"),
            SimpleNamespace(name="query_faq"),
            SimpleNamespace(name="create_ticket"),
        ]


class FakeExecutor:
    def __init__(self, result: ToolExecution | None = None) -> None:
        self.result = result
        self.calls: list[tuple[dict, int]] = []

    async def execute(self, tool_call: dict, conversation_id: int) -> ToolExecution:
        self.calls.append((tool_call, conversation_id))
        assert self.result is not None
        return self.result


def build_orchestrator(
    *,
    repository: FakeRepository | None = None,
    selector_reply: AIMessage | None = None,
    chunks: list[str] | None = None,
    stream_error: Exception | None = None,
    executor: FakeExecutor | None = None,
) -> tuple[ChatOrchestrator, FakeRepository, FakeChatModel, FakeRegistry, FakeExecutor]:
    repository = repository or FakeRepository()
    model = FakeChatModel(
        selector_reply or AIMessage(content="selector text is ignored"),
        chunks if chunks is not None else ["最终", "答复"],
        stream_error=stream_error,
    )
    registry = FakeRegistry()
    executor = executor or FakeExecutor()
    orchestrator = ChatOrchestrator(
        repository=repository,
        registry=registry,
        executor=executor,
        model=model,
        history_max_tokens=4000,
    )
    return orchestrator, repository, model, registry, executor


async def collect_events(orchestrator: ChatOrchestrator, **kwargs) -> list:
    return [event async for event in orchestrator.stream_turn(**kwargs)]


async def test_no_tool_still_streams_with_unbound_model_and_persists_final_answer() -> None:
    orchestrator, repository, model, registry, _ = build_orchestrator(
        chunks=["你", "好", ""]
    )

    events = await collect_events(
        orchestrator,
        user_id="user-1",
        message="你好",
        conversation_id=None,
    )

    assert events == [
        TokenEvent(content="你"),
        TokenEvent(content="好"),
        DoneEvent(conversation_id=1, tools=()),
    ]
    assert [(row.role, row.content) for row in repository.messages] == [
        ("user", "你好"),
        ("assistant", "你好"),
    ]
    assert len(model.astream_calls) == 1
    assert model.bind_calls == [
        (
            registry.model_tools,
            {"tool_choice": "auto", "parallel_tool_calls": False},
        )
    ]
    assert [tool.name for tool in model.bind_calls[0][0]] == [
        "query_order",
        "query_product",
        "query_logistics",
        "query_faq",
        "create_ticket",
    ]


async def test_one_tool_persists_trace_and_finalizes_with_matching_tool_message() -> None:
    tool_call = {
        "id": "call-1",
        "name": "query_logistics",
        "args": {"order_id": "1001"},
        "type": "tool_call",
    }
    tool_message = ToolMessage(
        content='{"ok":true,"tool":"query_logistics"}',
        name="query_logistics",
        tool_call_id="call-1",
        status="success",
    )
    execution = ToolExecution(
        name="query_logistics",
        ok=True,
        attempts=1,
        message=tool_message,
        payload={"ok": True, "tool": "query_logistics"},
    )
    executor = FakeExecutor(execution)
    orchestrator, repository, model, _, executor = build_orchestrator(
        selector_reply=AIMessage(content="", tool_calls=[tool_call]),
        chunks=["在", "路上"],
        executor=executor,
    )

    events = await collect_events(
        orchestrator,
        user_id="user-1",
        message="订单 1001 的物流到哪了",
        conversation_id=None,
    )

    assert events == [
        ToolEvent(name="query_logistics"),
        TokenEvent(content="在"),
        TokenEvent(content="路上"),
        DoneEvent(conversation_id=1, tools=("query_logistics",)),
    ]
    assert [row.role for row in repository.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert repository.messages[1].content is None
    assert repository.messages[1].tool_calls == [
        {
            "id": "call-1",
            "name": "query_logistics",
            "args": {"order_id": "1001"},
        }
    ]
    assert repository.messages[2].content == tool_message.content
    assert repository.messages[2].tool_call_id == "call-1"
    assert repository.messages[3].content == "在路上"
    assert executor.calls == [
        (
            {
                "id": "call-1",
                "name": "query_logistics",
                "args": {"order_id": "1001"},
            },
            1,
        )
    ]
    finalizer_messages = model.astream_calls[0]
    assert isinstance(finalizer_messages[-2], AIMessage)
    assert finalizer_messages[-2].tool_calls[0]["id"] == "call-1"
    assert finalizer_messages[-1] is tool_message


async def test_multiple_tool_calls_are_rejected_before_execution() -> None:
    selector_reply = AIMessage(
        content="",
        tool_calls=[
            {"id": "call-1", "name": "query_order", "args": {"order_id": "1"}},
            {
                "id": "call-2",
                "name": "query_logistics",
                "args": {"order_id": "1"},
            },
        ],
    )
    orchestrator, repository, model, _, executor = build_orchestrator(
        selector_reply=selector_reply
    )

    with pytest.raises(MultipleToolCalls):
        await collect_events(
            orchestrator,
            user_id="user-1",
            message="查订单和物流",
            conversation_id=None,
        )

    assert executor.calls == []
    assert model.astream_calls == []
    assert [(row.role, row.content) for row in repository.messages] == [
        ("user", "查订单和物流")
    ]


@pytest.mark.parametrize("owner", [None, "another-user"])
async def test_unknown_or_mismatched_conversation_is_rejected(owner: str | None) -> None:
    repository = FakeRepository()
    if owner is not None:
        repository.conversations[9] = owner
    orchestrator, repository, model, _, _ = build_orchestrator(repository=repository)

    with pytest.raises(ConversationNotFound):
        await collect_events(
            orchestrator,
            user_id="user-1",
            message="你好",
            conversation_id=9,
        )

    assert repository.messages == []
    assert model.bind_calls == []


async def test_empty_finalizer_output_is_not_persisted() -> None:
    orchestrator, repository, model, _, _ = build_orchestrator(chunks=["", ""])

    with pytest.raises(EmptyModelResponse):
        await collect_events(
            orchestrator,
            user_id="user-1",
            message="你好",
            conversation_id=None,
        )

    assert [row.role for row in repository.messages] == ["user"]
    assert len(model.astream_calls) == 1


async def test_partial_finalizer_failure_stores_no_final_answer_or_done() -> None:
    orchestrator, repository, _, _, _ = build_orchestrator(
        chunks=["部分"], stream_error=RuntimeError("upstream interrupted")
    )
    stream = orchestrator.stream_turn(
        user_id="user-1",
        message="你好",
        conversation_id=None,
    )

    assert await anext(stream) == TokenEvent(content="部分")
    with pytest.raises(RuntimeError, match="upstream interrupted"):
        await anext(stream)

    assert [row.role for row in repository.messages] == ["user"]


async def test_finalizer_is_the_original_unbound_model() -> None:
    orchestrator, _, model, _, _ = build_orchestrator(chunks=["完成"])

    await collect_events(
        orchestrator,
        user_id="user-1",
        message="你好",
        conversation_id=None,
    )

    assert len(model.selector.calls) == 1
    assert len(model.astream_calls) == 1
    assert model.astream_calls[0] is not model.selector.calls[0]


async def test_replay_includes_prior_final_answers_but_not_tool_traces() -> None:
    repository = FakeRepository()
    repository.conversations[7] = "user-1"
    repository.next_conversation_id = 8
    await repository.append_message(7, "user", "旧问题")
    await repository.append_message(
        7,
        "assistant",
        None,
        tool_calls=[
            {"id": "old-call", "name": "query_order", "args": {"order_id": "1"}}
        ],
    )
    await repository.append_message(
        7,
        "tool",
        '{"ok":true}',
        tool_call_id="old-call",
    )
    await repository.append_message(7, "assistant", "旧答案")
    orchestrator, _, model, _, _ = build_orchestrator(repository=repository)

    await collect_events(
        orchestrator,
        user_id="user-1",
        message="新问题",
        conversation_id=7,
    )

    selector_messages = model.selector.calls[0]
    assert isinstance(selector_messages[0], SystemMessage)
    natural_messages = selector_messages[1:]
    assert [type(message) for message in natural_messages] == [
        HumanMessage,
        AIMessage,
        HumanMessage,
    ]
    assert [message.content for message in natural_messages] == [
        "旧问题",
        "旧答案",
        "新问题",
    ]
    assert all(message.content != '{"ok":true}' for message in natural_messages)

