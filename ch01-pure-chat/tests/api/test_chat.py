from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from app.api.dependencies import get_chat_model
from app.core.config import Settings, get_settings
from app.main import create_app


class FakeModel:
    def __init__(self, chunks=None, error: Exception | None = None) -> None:
        self.chunks = chunks or []
        self.error = error

    async def astream(self, messages):
        for content in self.chunks:
            yield AIMessageChunk(content=content)
        if self.error:
            raise self.error


def chat_settings() -> Settings:
    return Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        history_max_tokens=4000,
        _env_file=None,
    )


def make_client(model: FakeModel) -> TestClient:
    application = create_app(settings_loader=chat_settings)
    application.dependency_overrides[get_settings] = chat_settings
    application.dependency_overrides[get_chat_model] = lambda: model
    return TestClient(application)


def test_chat_stream_emits_token_events_then_done() -> None:
    with make_client(FakeModel(["你", "好"])) as client:
        response = client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        'event: token\ndata: {"content":"你"}\n\n'
        'event: token\ndata: {"content":"好"}\n\n'
        "event: done\ndata: {}\n\n"
    )


def test_chat_stream_emits_error_without_done_after_partial_output() -> None:
    with make_client(FakeModel(["先"], RuntimeError("secret body"))) as client:
        response = client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    assert response.text.count('event: token\ndata: {"content":"先"}') == 1
    assert response.text.count(
        'event: error\ndata: {"code":"upstream_error","message":"模型服务暂时不可用"}'
    ) == 1
    assert "event: done" not in response.text
    assert "secret body" not in response.text


def test_chat_rejects_latest_message_over_budget() -> None:
    def tiny_settings() -> Settings:
        return Settings(
            chat_base_url="https://example.test/v1",
            chat_api_key="secret",
            chat_model="example-model",
            history_max_tokens=1,
            _env_file=None,
        )

    application = create_app(settings_loader=tiny_settings)
    application.dependency_overrides[get_settings] = tiny_settings
    application.dependency_overrides[get_chat_model] = lambda: FakeModel(["unused"])
    with TestClient(application) as client:
        response = client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "this message is too long"}]},
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "latest user message exceeds history token budget"
