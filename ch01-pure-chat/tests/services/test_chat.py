import logging

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage

from app.schemas.chat import ChatRequest
from app.services.chat import prepare_chat_messages, stream_chat


class FakeStreamingModel:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.seen_messages = None

    async def astream(self, messages):
        self.seen_messages = messages
        for content in self.chunks:
            yield AIMessageChunk(content=content)


async def test_stream_chat_skips_empty_chunks_and_preserves_order() -> None:
    model = FakeStreamingModel(["你", "", "好"])
    result = [chunk async for chunk in stream_chat([HumanMessage(content="hi")], model)]
    assert result == ["你", "好"]


async def test_stream_chat_logs_warning_when_all_chunks_are_empty(caplog) -> None:
    model = FakeStreamingModel(["", ""])
    with caplog.at_level(logging.WARNING):
        result = [chunk async for chunk in stream_chat([HumanMessage(content="hi")], model)]
    assert result == []
    assert "chat model stream returned no text" in caplog.text


def test_prepare_chat_messages_adds_system_prompt_and_keeps_latest_user() -> None:
    request = ChatRequest(messages=[{"role": "user", "content": "订单 A123"}])
    messages = prepare_chat_messages(request, max_tokens=100)
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[-1], HumanMessage)
    assert messages[-1].content == "订单 A123"
