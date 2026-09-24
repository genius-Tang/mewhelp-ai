import asyncio
import json
from typing import Annotated, Any, Literal

import pytest
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel, Field

from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, ToolSpec


class ValueInput(BaseModel):
    value: str = Field(min_length=1)


def _registry(
    tool_instance: Any,
    *,
    read_only: bool = True,
    timeout_seconds: float = 0.05,
    max_attempts: int = 2,
    inject_conversation_id: bool = False,
) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                tool=tool_instance,
                read_only=read_only,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                inject_conversation_id=inject_conversation_id,
            )
        ]
    )


def _call(name: str, args: object, call_id: str = "call-123") -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _content(execution: Any) -> dict[str, Any]:
    return json.loads(execution.message.content)


@pytest.mark.asyncio
async def test_unknown_tool_returns_safe_failed_tool_message() -> None:
    registry = ToolRegistry([])

    execution = await ToolExecutor(registry).execute(
        _call("not_registered", {}), conversation_id=41
    )

    assert execution.name == "not_registered"
    assert execution.ok is False
    assert execution.attempts == 0
    assert execution.message.status == "error"
    assert execution.message.tool_call_id == "call-123"
    assert execution.payload == {
        "ok": False,
        "tool": "not_registered",
        "error": {"code": "unknown_tool", "message": "未知工具"},
    }
    assert _content(execution) == execution.payload


@pytest.mark.asyncio
async def test_visible_schema_validation_prevents_execution() -> None:
    calls = 0

    @tool(args_schema=ValueInput)
    async def validated_tool(value: str) -> dict[str, str]:
        """Return a value after model-visible validation."""
        nonlocal calls
        calls += 1
        return {"value": value}

    execution = await ToolExecutor(_registry(validated_tool)).execute(
        _call("validated_tool", {"value": ""}), conversation_id=41
    )

    assert calls == 0
    assert execution.ok is False
    assert execution.attempts == 0
    assert execution.message.status == "error"
    assert execution.message.tool_call_id == "call-123"
    assert execution.payload["error"] == {
        "code": "invalid_arguments",
        "message": "工具参数无效",
    }


@pytest.mark.asyncio
async def test_unexpected_visible_argument_is_rejected_instead_of_ignored() -> None:
    calls = 0

    @tool(args_schema=ValueInput)
    async def strict_tool(value: str) -> dict[str, str]:
        """Reject model arguments not declared by the visible schema."""
        nonlocal calls
        calls += 1
        return {"value": value}

    execution = await ToolExecutor(_registry(strict_tool)).execute(
        _call("strict_tool", {"value": "ok", "unexpected": "secret"}),
        conversation_id=41,
    )

    assert calls == 0
    assert execution.attempts == 0
    assert execution.payload["error"]["code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_conversation_id_is_injected_only_after_visible_validation() -> None:
    received: list[tuple[str, Literal["售后"], int]] = []

    @tool
    async def ticket_tool(
        description: str,
        ticket_type: Literal["售后"],
        conversation_id: Annotated[int, InjectedToolArg],
    ) -> dict[str, object]:
        """Create a test ticket with a trusted conversation identifier."""
        received.append((description, ticket_type, conversation_id))
        return {"ticket_no": "T-1", "conversation_id": conversation_id}

    assert "conversation_id" not in ticket_tool.tool_call_schema.model_fields
    execution = await ToolExecutor(
        _registry(
            ticket_tool,
            read_only=False,
            max_attempts=1,
            inject_conversation_id=True,
        )
    ).execute(
        _call(
            "ticket_tool",
            {"description": "需要人工", "ticket_type": "售后"},
        ),
        conversation_id=87,
    )

    assert received == [("需要人工", "售后", 87)]
    assert execution.ok is True
    assert execution.payload["data"]["conversation_id"] == 87


@pytest.mark.asyncio
async def test_wrong_enum_is_rejected_before_trusted_injection() -> None:
    calls = 0

    @tool
    async def ticket_tool(
        ticket_type: Literal["售后"],
        conversation_id: Annotated[int, InjectedToolArg],
    ) -> dict[str, int]:
        """Create a typed test ticket."""
        nonlocal calls
        calls += 1
        return {"conversation_id": conversation_id}

    execution = await ToolExecutor(
        _registry(
            ticket_tool,
            read_only=False,
            max_attempts=1,
            inject_conversation_id=True,
        )
    ).execute(
        _call("ticket_tool", {"ticket_type": "其他"}), conversation_id=87
    )

    assert calls == 0
    assert execution.attempts == 0
    assert execution.payload["error"]["code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_read_tool_retries_one_timeout_then_succeeds() -> None:
    calls = 0

    @tool(args_schema=ValueInput)
    async def flaky_read(value: str) -> dict[str, str]:
        """Succeed after one transient timeout."""
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("first transient failure contains api-key-123")
        return {"value": value}

    execution = await ToolExecutor(
        _registry(flaky_read, max_attempts=2)
    ).execute(_call("flaky_read", {"value": "中文"}), conversation_id=41)

    assert calls == 2
    assert execution.ok is True
    assert execution.attempts == 2
    assert execution.message.status == "success"
    assert execution.message.tool_call_id == "call-123"
    assert execution.message.content == (
        '{"ok":true,"tool":"flaky_read","data":{"value":"中文"}}'
    )
    assert execution.payload == {
        "ok": True,
        "tool": "flaky_read",
        "data": {"value": "中文"},
    }


@pytest.mark.asyncio
async def test_read_tool_stops_at_configured_timeout_attempts() -> None:
    calls = 0

    @tool(args_schema=ValueInput)
    async def slow_read(value: str) -> dict[str, str]:
        """Take longer than the configured execution timeout."""
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"value": value}

    execution = await ToolExecutor(
        _registry(slow_read, timeout_seconds=0.001, max_attempts=3)
    ).execute(_call("slow_read", {"value": "ok"}), conversation_id=41)

    assert calls == 3
    assert execution.ok is False
    assert execution.attempts == 3
    assert execution.message.status == "error"
    assert execution.payload == {
        "ok": False,
        "tool": "slow_read",
        "error": {"code": "timeout", "message": "工具暂时不可用"},
    }


@pytest.mark.asyncio
async def test_write_tool_never_retries_transient_failure() -> None:
    calls = 0

    @tool(args_schema=ValueInput)
    async def failing_write(value: str) -> dict[str, str]:
        """Fail a write operation with a transient-looking exception."""
        nonlocal calls
        calls += 1
        raise ConnectionError("database://user:password@private-host")

    execution = await ToolExecutor(
        _registry(failing_write, read_only=False, max_attempts=3)
    ).execute(_call("failing_write", {"value": "ok"}), conversation_id=41)

    assert calls == 1
    assert execution.ok is False
    assert execution.attempts == 1
    assert execution.payload["error"] == {
        "code": "execution_error",
        "message": "工具执行失败",
    }


@pytest.mark.asyncio
async def test_execution_error_content_never_contains_raw_exception_details() -> None:
    secret = "api-key-raw-secret"

    @tool(args_schema=ValueInput)
    async def broken_tool(value: str) -> dict[str, str]:
        """Raise a deterministic business execution error."""
        raise RuntimeError(f"upstream rejected {secret} at mysql://private")

    execution = await ToolExecutor(_registry(broken_tool)).execute(
        _call("broken_tool", {"value": "ok"}, call_id="call-error"),
        conversation_id=41,
    )

    assert execution.ok is False
    assert execution.attempts == 1
    assert execution.message.status == "error"
    assert execution.message.tool_call_id == "call-error"
    assert execution.payload["error"] == {
        "code": "execution_error",
        "message": "工具执行失败",
    }
    assert secret not in execution.message.content
    assert "mysql://private" not in execution.message.content
