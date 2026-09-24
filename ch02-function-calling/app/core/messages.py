from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

TokenCounter = Callable[[Sequence[BaseMessage]], int]


class MessageBudgetExceeded(ValueError):
    """Raised when the latest user message alone exceeds the history budget."""


class ReplayMessage(Protocol):
    role: str
    content: str | None


def to_langchain_messages(messages: Iterable[ReplayMessage]) -> list[BaseMessage]:
    """Convert natural replay rows without depending on ORM model classes."""

    converted: list[BaseMessage] = []
    for message in messages:
        if message.role == "user" and message.content is not None:
            converted.append(HumanMessage(content=message.content))
        elif message.role == "assistant" and message.content:
            converted.append(AIMessage(content=message.content))
    return converted


def trim_history(
    messages: list[BaseMessage],
    max_tokens: int,
    token_counter: TokenCounter = count_tokens_approximately,
) -> list[BaseMessage]:
    latest = messages[-1]
    if token_counter([latest]) > max_tokens:
        raise MessageBudgetExceeded("latest user message exceeds history token budget")

    trimmed = trim_messages(
        messages,
        strategy="last",
        token_counter=token_counter,
        max_tokens=max_tokens,
        start_on="human",
        end_on="human",
        allow_partial=False,
    )
    return list(trimmed)
