from langchain_openai import ChatOpenAI

from app.core.config import Settings


def create_chat_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=str(settings.chat_base_url).rstrip("/"),
        api_key=settings.chat_api_key.get_secret_value(),
        model=settings.chat_model,
    )
