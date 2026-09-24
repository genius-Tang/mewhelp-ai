from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.messages import MessageBudgetExceeded, to_langchain_messages, trim_history


@dataclass
class ReplayRow:
    role: str
    content: str | None


def word_counter(messages) -> int:
    return sum(len(message.content.split()) for message in messages)


def test_to_langchain_messages_preserves_roles_and_order() -> None:
    result = to_langchain_messages(
        [
            ReplayRow(role="user", content="first"),
            ReplayRow(role="assistant", content="second"),
            ReplayRow(role="user", content="third"),
        ]
    )
    assert [type(message) for message in result] == [HumanMessage, AIMessage, HumanMessage]
    assert [message.content for message in result] == ["first", "second", "third"]


def test_trim_history_drops_oldest_complete_messages() -> None:
    messages = [
        HumanMessage(content="old question"),
        AIMessage(content="old answer"),
        HumanMessage(content="new question"),
    ]
    result = trim_history(messages, max_tokens=4, token_counter=word_counter)
    assert result == [HumanMessage(content="new question")]
    assert isinstance(result[0], HumanMessage)
    assert result[-1].content == "new question"


def test_trim_history_rejects_latest_message_over_budget() -> None:
    with pytest.raises(MessageBudgetExceeded):
        trim_history(
            [HumanMessage(content="one two three")],
            max_tokens=2,
            token_counter=word_counter,
        )
