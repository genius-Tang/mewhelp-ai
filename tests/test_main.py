from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def valid_settings() -> Settings:
    return Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        _env_file=None,
    )


def test_app_validates_settings_during_lifespan() -> None:
    calls = []

    def loader() -> Settings:
        calls.append("loaded")
        return valid_settings()

    with TestClient(create_app(settings_loader=loader)):
        pass

    assert calls == ["loaded"]
