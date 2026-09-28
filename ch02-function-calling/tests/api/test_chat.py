from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_chat_orchestrator
from app.core.config import Settings
from app.db.repository import TurnBusy
from app.main import create_app
from app.services.chat import (
    ConversationNotFound,
    DoneEvent,
    MultipleToolCalls,
    TokenEvent,
    ToolEvent,
)


class FakeOrchestrator:
    def __init__(
        self,
        events: list[ToolEvent | TokenEvent | DoneEvent] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.events = events or []
        self.error = error
        self.calls: list[tuple[str, str, int | None]] = []

    async def stream_turn(
        self,
        user_id: str,
        message: str,
        conversation_id: int | None,
    ) -> AsyncIterator[ToolEvent | TokenEvent | DoneEvent]:
        self.calls.append((user_id, message, conversation_id))
        for event in self.events:
            yield event
        if self.error is not None:
            raise self.error


def chat_settings() -> Settings:
    return Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        database_url="mysql+asyncmy://user:password@localhost/mewhelp",
        test_database_url="mysql+asyncmy://user:password@localhost/mewhelp_test",
        history_max_tokens=4000,
        _env_file=None,
    )


def make_client(orchestrator: FakeOrchestrator) -> TestClient:
    application = create_app(settings_loader=chat_settings)
    application.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator
    return TestClient(application)


def test_chat_stream_emits_tool_tokens_and_done_in_order() -> None:
    orchestrator = FakeOrchestrator(
        [
            ToolEvent(name="query_logistics"),
            TokenEvent(content="您的"),
            TokenEvent(content="订单"),
            DoneEvent(conversation_id=12, tools=("query_logistics",)),
        ]
    )

    with make_client(orchestrator) as client:
        response = client.post(
            "/chat/stream",
            json={
                "user_id": " browser-user ",
                "message": " 订单 1001 的物流到哪了 ",
                "conversation_id": 12,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text == (
        'event: tool\ndata: {"name":"query_logistics","status":"running"}\n\n'
        'event: token\ndata: {"content":"您的"}\n\n'
        'event: token\ndata: {"content":"订单"}\n\n'
        'event: done\ndata: {"conversation_id":12,"tools":["query_logistics"]}\n\n'
    )
    assert orchestrator.calls == [("browser-user", "订单 1001 的物流到哪了", 12)]


def test_chat_stream_without_tool_emits_only_tokens_and_done() -> None:
    orchestrator = FakeOrchestrator(
        [
            TokenEvent(content="您好"),
            DoneEvent(conversation_id=3, tools=()),
        ]
    )

    with make_client(orchestrator) as client:
        response = client.post(
            "/chat/stream",
            json={"user_id": "user-3", "message": "你好"},
        )

    assert response.text == (
        'event: token\ndata: {"content":"您好"}\n\n'
        'event: done\ndata: {"conversation_id":3,"tools":[]}\n\n'
    )
    assert "event: tool" not in response.text


def test_chat_stream_stops_after_done_event() -> None:
    orchestrator = FakeOrchestrator(
        [
            DoneEvent(conversation_id=3, tools=()),
            TokenEvent(content="must not be emitted"),
        ]
    )

    with make_client(orchestrator) as client:
        response = client.post(
            "/chat/stream",
            json={"user_id": "user-3", "message": "你好"},
        )

    assert response.text == (
        'event: done\ndata: {"conversation_id":3,"tools":[]}\n\n'
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ConversationNotFound("private conversation details"),
            'event: error\ndata: {"code":"conversation_not_found","message":"会话不存在"}\n\n',
        ),
        (
            MultipleToolCalls("provider returned secret payload"),
            'event: error\ndata: {"code":"multiple_tool_calls","message":"模型返回了多个工具调用"}\n\n',
        ),
        (
            TurnBusy("private lock details"),
            'event: error\ndata: {"code":"conversation_busy","message":"上一条消息仍在处理中，请稍后重试"}\n\n',
        ),
        (
            SQLAlchemyError("mysql+asyncmy://user:password@host/database"),
            'event: error\ndata: {"code":"database_error","message":"数据库暂时不可用"}\n\n',
        ),
        (
            RuntimeError("secret upstream body"),
            'event: error\ndata: {"code":"upstream_error","message":"模型服务暂时不可用"}\n\n',
        ),
    ],
)
def test_chat_stream_maps_failures_to_one_terminal_safe_error(
    error: Exception,
    expected: str,
) -> None:
    orchestrator = FakeOrchestrator(
        events=[TokenEvent(content="partial")],
        error=error,
    )

    with make_client(orchestrator) as client:
        response = client.post(
            "/chat/stream",
            json={"user_id": "user-7", "message": "继续"},
        )

    assert response.status_code == 200
    assert response.text.endswith(expected)
    assert response.text.count("event: error") == 1
    assert "event: done" not in response.text
    assert str(error) not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": " ", "message": "hello"},
        {"user_id": "u" * 65, "message": "hello"},
        {"user_id": "user", "message": " \t\n "},
        {"user_id": "user", "message": "m" * 4001},
        {"user_id": "user", "message": "hello", "conversation_id": 0},
    ],
)
def test_chat_rejects_invalid_request_before_opening_stream(payload: dict) -> None:
    orchestrator = FakeOrchestrator()

    with make_client(orchestrator) as client:
        response = client.post("/chat/stream", json=payload)

    assert response.status_code == 422
    assert orchestrator.calls == []
