from typing import Annotated

from fastapi import Depends, Request
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings
from app.core.model import create_chat_model
from app.services.chat import ChatOrchestrator


def get_chat_model(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatOpenAI:
    return create_chat_model(settings)


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    return request.app.state.chat_orchestrator
