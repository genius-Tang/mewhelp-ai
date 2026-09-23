from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


StructuredOutputMethod = Literal["function_calling", "json_mode", "json_schema"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    chat_base_url: AnyHttpUrl
    chat_api_key: SecretStr = Field(min_length=1)
    chat_model: str = Field(min_length=1)
    chat_structured_output_method: StructuredOutputMethod = "function_calling"
    history_max_tokens: PositiveInt = 4000


@lru_cache
def get_settings() -> Settings:
    return Settings()
