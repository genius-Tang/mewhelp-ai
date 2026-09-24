import asyncio
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.tools.registry import ToolRegistry, ToolSpec


_TRANSIENT_EXCEPTIONS = (TimeoutError, ConnectionError, OperationalError)


@dataclass(frozen=True, slots=True)
class ToolExecution:
    name: str
    ok: bool
    attempts: int
    message: ToolMessage
    payload: dict[str, Any]


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        tool_call: dict[str, Any],
        conversation_id: int,
    ) -> ToolExecution:
        name = tool_call.get("name")
        call_id = tool_call.get("id")
        safe_name = name if isinstance(name, str) else ""
        safe_call_id = call_id if isinstance(call_id, str) else ""

        spec = self._registry.get(safe_name)
        if spec is None:
            return self._failure(
                name=safe_name,
                call_id=safe_call_id,
                attempts=0,
                code="unknown_tool",
                message="未知工具",
            )

        arguments = tool_call.get("args", {})
        visible = self._validate_visible_arguments(spec, arguments)
        if visible is None:
            return self._failure(
                name=safe_name,
                call_id=safe_call_id,
                attempts=0,
                code="invalid_arguments",
                message="工具参数无效",
            )

        if spec.inject_conversation_id:
            visible["conversation_id"] = conversation_id

        attempts = 0
        while True:
            attempts += 1
            try:
                result = await asyncio.wait_for(
                    spec.tool.ainvoke(visible),
                    timeout=spec.timeout_seconds,
                )
                payload = {
                    "ok": True,
                    "tool": safe_name,
                    "data": result,
                }
                return self._execution(
                    name=safe_name,
                    call_id=safe_call_id,
                    attempts=attempts,
                    ok=True,
                    payload=payload,
                )
            except _TRANSIENT_EXCEPTIONS as exc:
                if spec.read_only and attempts < spec.max_attempts:
                    continue
                code = "timeout" if isinstance(exc, TimeoutError) else "execution_error"
                message = "工具暂时不可用" if code == "timeout" else "工具执行失败"
                return self._failure(
                    name=safe_name,
                    call_id=safe_call_id,
                    attempts=attempts,
                    code=code,
                    message=message,
                )
            except Exception:
                return self._failure(
                    name=safe_name,
                    call_id=safe_call_id,
                    attempts=attempts,
                    code="execution_error",
                    message="工具执行失败",
                )

    @staticmethod
    def _validate_visible_arguments(
        spec: ToolSpec,
        arguments: object,
    ) -> dict[str, Any] | None:
        if not isinstance(arguments, dict):
            return None
        schema = spec.tool.tool_call_schema
        if set(arguments) - set(schema.model_fields):
            return None
        try:
            return schema.model_validate(arguments).model_dump()
        except ValidationError:
            return None

    @classmethod
    def _failure(
        cls,
        *,
        name: str,
        call_id: str,
        attempts: int,
        code: str,
        message: str,
    ) -> ToolExecution:
        payload = {
            "ok": False,
            "tool": name,
            "error": {"code": code, "message": message},
        }
        return cls._execution(
            name=name,
            call_id=call_id,
            attempts=attempts,
            ok=False,
            payload=payload,
        )

    @staticmethod
    def _execution(
        *,
        name: str,
        call_id: str,
        attempts: int,
        ok: bool,
        payload: dict[str, Any],
    ) -> ToolExecution:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        message = ToolMessage(
            content=content,
            name=name,
            tool_call_id=call_id,
            status="success" if ok else "error",
        )
        return ToolExecution(
            name=name,
            ok=ok,
            attempts=attempts,
            message=message,
            payload=payload,
        )
