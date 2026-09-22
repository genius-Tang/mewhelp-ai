import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage

from app.core.messages import to_langchain_messages, trim_history
from app.core.prompts import build_chat_prompt_messages
from app.schemas.chat import ChatRequest


logger = logging.getLogger(__name__)


def prepare_chat_messages(request: ChatRequest, max_tokens: int) -> list[BaseMessage]:
    history = to_langchain_messages(request.messages)
    trimmed = trim_history(history, max_tokens=max_tokens)
    return build_chat_prompt_messages(trimmed)


async def stream_chat(messages: list[BaseMessage], model: Any) -> AsyncIterator[str]:
    emitted_text = False
    async for chunk in model.astream(messages):
        text = chunk.text
        if text:
            emitted_text = True
            yield text
    if not emitted_text:
        logger.warning("chat model stream returned no text")
