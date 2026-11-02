from collections.abc import Callable
from typing import Any

from ..tool_definition import ToolDefinition


ToolHandler = Callable[..., Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(
        self, definition: ToolDefinition, handler: ToolHandler, *, replace: bool = False
    ) -> None:
        if definition.name in self._definitions and not replace:
            raise ValueError(f"Tool is already registered: {definition.name}")
        if not callable(handler):
            raise TypeError("Tool handlers must be callable.")
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def get(self, name: str) -> tuple[ToolDefinition, ToolHandler]:
        try:
            return self._definitions[name], self._handlers[name]
        except KeyError as error:
            raise KeyError(f"Unknown tool: {name}") from error

    def discover(self) -> list[ToolDefinition]:
        return [self._definitions[name] for name in sorted(self._definitions)]

    def model_schemas(self) -> list[dict[str, Any]]:
        return [definition.model_tool_schema() for definition in self.discover()]

    def remove(self, name: str) -> None:
        if name not in self._definitions:
            raise KeyError(f"Unknown tool: {name}")
        del self._definitions[name]
        del self._handlers[name]