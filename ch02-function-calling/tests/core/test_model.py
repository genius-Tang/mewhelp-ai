from unittest.mock import patch

from app.core.config import Settings
from app.core.model import create_chat_model


def test_create_chat_model_uses_openai_compatible_settings() -> None:
    settings = Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        database_url="mysql+asyncmy://user:password@localhost/mewhelp",
        test_database_url="mysql+asyncmy://user:password@localhost/mewhelp_test",
        _env_file=None,
    )
    with patch("app.core.model.ChatOpenAI") as model_class:
        create_chat_model(settings)

    model_class.assert_called_once_with(
        base_url="https://example.test/v1",
        api_key="secret",
        model="example-model",
    )
