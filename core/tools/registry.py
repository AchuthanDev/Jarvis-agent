"""Tool registry.

Holds the typed tools the agent may call. Instances are owned by the
application (stored on ``app.state``); there is no process-global registry.
"""

from __future__ import annotations

from typing import Any

from core.tools.base import Tool


class ToolNotFoundError(KeyError):
    """No tool with the requested name is registered."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return [self._tools[name] for name in self.names()]

    def describe(self) -> str:
        """Prompt text listing every available tool."""
        lines = [tool.describe() for tool in self.all()]
        return "\n".join(lines) if lines else "(no tools available)"

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Structured metadata (for future native function-calling support)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "risk": tool.risk,
                "timeout": tool.timeout,
            }
            for tool in self.all()
        ]
