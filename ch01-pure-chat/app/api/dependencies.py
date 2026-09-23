from typing import Annotated

from fastapi import Depends
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings
from app.core.model import create_chat_model


def get_chat_model(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatOpenAI:
    return create_chat_model(settings)
