from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def valid_settings() -> Settings:
    return Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        database_url="mysql+asyncmy://user:password@localhost/mewhelp",
        test_database_url="mysql+asyncmy://user:password@localhost/mewhelp_test",
        tool_timeout_seconds=2.5,
        tool_max_attempts=3,
        _env_file=None,
    )


def test_app_builds_runtime_once_with_expected_tool_policies(monkeypatch) -> None:
    engine = AsyncMock()
    engine.dispose = AsyncMock()
    session_factory = object()
    calls: list[object] = []

    def loader() -> Settings:
        calls.append("settings")
        return valid_settings()

    def make_engine(settings: Settings):
        calls.append(settings)
        return engine

    def make_session_factory(received_engine):
        calls.append(received_engine)
        return session_factory

    monkeypatch.setattr("app.main.create_database_engine", make_engine)
    monkeypatch.setattr("app.main.create_session_factory", make_session_factory)

    application = create_app(settings_loader=loader)
    with TestClient(application):
        orchestrator = application.state.chat_orchestrator
        registry = orchestrator._registry

        assert calls == ["settings", valid_settings(), engine]
        assert orchestrator._repository._session_factory is session_factory
        assert orchestrator._executor._registry is registry
        assert orchestrator._history_max_tokens == valid_settings().history_max_tokens
        assert [tool.name for tool in registry.model_tools] == [
            "query_order",
            "query_product",
            "query_logistics",
            "query_faq",
            "create_ticket",
        ]
        for name in (
            "query_order",
            "query_product",
            "query_logistics",
            "query_faq",
        ):
            spec = registry.get(name)
            assert spec is not None
            assert spec.read_only is True
            assert spec.timeout_seconds == 2.5
            assert spec.max_attempts == 3
            assert spec.inject_conversation_id is False

        ticket_spec = registry.get("create_ticket")
        assert ticket_spec is not None
        assert ticket_spec.read_only is False
        assert ticket_spec.timeout_seconds == 2.5
        assert ticket_spec.max_attempts == 1
        assert ticket_spec.inject_conversation_id is True

    engine.dispose.assert_awaited_once_with()


def test_app_disposes_engine_when_lifespan_body_fails(monkeypatch) -> None:
    engine = AsyncMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr("app.main.create_database_engine", lambda settings: engine)

    def fail_to_create_session_factory(received_engine):
        assert received_engine is engine
        raise RuntimeError("runtime assembly failed")

    monkeypatch.setattr(
        "app.main.create_session_factory",
        fail_to_create_session_factory,
    )

    with pytest.raises(RuntimeError, match="runtime assembly failed"):
        with TestClient(create_app(settings_loader=valid_settings)):
            pass

    engine.dispose.assert_awaited_once_with()


def test_app_serves_chat_page_and_static_assets() -> None:
    with TestClient(create_app(settings_loader=valid_settings)) as client:
        page = client.get("/")
        script = client.get("/static/chat.js")

    assert page.status_code == 200
    assert "MewHelp 智能客服" in page.text
    assert 'fetch("/chat/stream"' in script.text
    assert 'user_id: userId, message, conversation_id: conversationId' in script.text
    assert "messages }" not in script.text
    assert 'mewhelp_conversation_id' in script.text
