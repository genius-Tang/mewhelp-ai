from collections.abc import Sequence

import pytest
from langchain_core.tools import BaseTool, tool

from app.tools.registry import ToolRegistry, ToolSpec


@tool
async def first_tool(value: str) -> dict[str, str]:
    """Return the supplied value from the first test tool."""
    return {"value": value}


@tool
async def second_tool(value: str) -> dict[str, str]:
    """Return the supplied value from the second test tool."""
    return {"value": value}


def _spec(tool_instance: BaseTool, **overrides: object) -> ToolSpec:
    values: dict[str, object] = {
        "tool": tool_instance,
        "read_only": True,
        "timeout_seconds": 1.0,
        "max_attempts": 2,
    }
    values.update(overrides)
    return ToolSpec(**values)  # type: ignore[arg-type]


def test_registry_preserves_registration_order_and_returns_tools_only() -> None:
    specs: Sequence[ToolSpec] = [_spec(first_tool), _spec(second_tool)]

    registry = ToolRegistry(specs)

    assert registry.model_tools == [first_tool, second_tool]
    assert all(isinstance(item, BaseTool) for item in registry.model_tools)
    assert registry.get("first_tool") is specs[0]
    assert registry.get("second_tool") is specs[1]
    assert registry.get("missing") is None


def test_registry_rejects_duplicate_tool_names() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ToolRegistry([_spec(first_tool), _spec(first_tool)])


def test_registry_rejects_blank_tool_name() -> None:
    original_name = first_tool.name
    first_tool.name = "   "
    try:
        with pytest.raises(ValueError, match="name"):
            ToolRegistry([_spec(first_tool)])
    finally:
        first_tool.name = original_name


@pytest.mark.parametrize(
    ("field", "value"),
    [("timeout_seconds", 0.0), ("timeout_seconds", -1.0), ("max_attempts", 0)],
)
def test_tool_spec_rejects_invalid_execution_policy(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _spec(first_tool, **{field: value})
