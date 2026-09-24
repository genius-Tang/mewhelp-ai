from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.tools import BaseTool


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool: BaseTool
    read_only: bool
    timeout_seconds: float
    max_attempts: int
    inject_conversation_id: bool = False

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


class ToolRegistry:
    def __init__(self, specs: Sequence[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            name = spec.tool.name
            if not name.strip():
                raise ValueError("tool name must not be empty")
            if name in self._specs:
                raise ValueError(f"duplicate tool name: {name}")
            self._specs[name] = spec

    @property
    def model_tools(self) -> list[BaseTool]:
        return [spec.tool for spec in self._specs.values()]

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)
