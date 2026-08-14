"""Tool definitions and execution context.

A :class:`Tool` is the single typed capability JARVIS can invoke. Tools are
registered in a :class:`ToolRegistry` and are executed only after validation
and a permission check (see ``core/security``).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from core.tools.errors import ToolExecutionError
from core.tools.validation import validate_arguments

# Risk levels mirror docs/SECURITY.md.
RISK_READ_ONLY = 0
RISK_SAFE = 1
RISK_APPROVAL = 2
RISK_SENSITIVE = 3


@dataclass(slots=True)
class ToolContext:
    """Runtime dependencies passed to every tool execution.

    Tools never reach for globals; whatever they need comes through here.
    """

    session: Any = None  # optional AsyncSession for DB-backed tools
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    device_id: UUID | None = None


ToolFn = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class Tool:
    """A single capability exposed to the agent."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn
    risk: int = RISK_READ_ONLY
    timeout: float = 30.0
    # Argument names whose values are redacted in audit logs (e.g. secrets).
    redact: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description:
            raise ValueError(f"tool {self.name!r} needs a description")

    async def run(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        """Validate ``arguments`` against the declared schema, then execute."""
        validate_arguments(self.parameters, arguments)
        try:
            return await self.fn(**arguments, context=context)
        except Exception as exc:
            raise ToolExecutionError(
                f"tool {self.name!r} failed: {type(exc).__name__}: {exc}"
            ) from exc

    def describe(self) -> str:
        """Compact, prompt-friendly description of the tool."""
        params = json.dumps(self.parameters, separators=(",", ":")) if self.parameters else ""
        return f"- {self.name}: {self.description}  Parameters: {params}"


@dataclass(slots=True)
class ToolResult:
    """Outcome of one tool call, ready for audit logging."""

    name: str
    arguments: dict[str, Any]
    status: str  # executed | failed | denied | validation_error | not_found
    output: str = ""
    error: str | None = None
    duration_ms: int | None = None
    denied_reason: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)
