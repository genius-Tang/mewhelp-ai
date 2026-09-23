import pytest
from pydantic import ValidationError

from app.core.config import Settings


CHAT_ENV_KEYS = (
    "CHAT_BASE_URL",
    "CHAT_API_KEY",
    "CHAT_MODEL",
    "CHAT_STRUCTURED_OUTPUT_METHOD",
    "HISTORY_MAX_TOKENS",
)


def clear_chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CHAT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_load_required_values_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("CHAT_API_KEY", "secret")
    monkeypatch.setenv("CHAT_MODEL", "example-model")

    settings = Settings(_env_file=None)

    assert str(settings.chat_base_url) == "https://example.test/v1"
    assert settings.chat_api_key.get_secret_value() == "secret"
    assert settings.chat_model == "example-model"
    assert settings.chat_structured_output_method == "function_calling"
    assert settings.history_max_tokens == 4000


def test_settings_reject_missing_required_values(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_chat_env(monkeypatch)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    message = str(exc_info.value)
    assert "chat_base_url" in message
    assert "chat_api_key" in message
    assert "chat_model" in message


def test_settings_reject_blank_required_values(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_BASE_URL", " ")
    monkeypatch.setenv("CHAT_API_KEY", " ")
    monkeypatch.setenv("CHAT_MODEL", " ")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_reject_non_positive_budget(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("CHAT_API_KEY", "secret")
    monkeypatch.setenv("CHAT_MODEL", "example-model")
    monkeypatch.setenv("HISTORY_MAX_TOKENS", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_validation_does_not_expose_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("CHAT_API_KEY", "super-secret-value")
    monkeypatch.setenv("CHAT_MODEL", "example-model")
    monkeypatch.setenv("HISTORY_MAX_TOKENS", "0")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "super-secret-value" not in str(exc_info.value)


def test_settings_ignore_unrelated_dotenv_fields(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CHAT_BASE_URL=https://example.test/v1\n"
        "CHAT_API_KEY=secret\n"
        "CHAT_MODEL=example-model\n"
        "UNRELATED_SETTING=value\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.chat_model == "example-model"
