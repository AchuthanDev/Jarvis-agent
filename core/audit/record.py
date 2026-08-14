"""Audit trail for tool calls.

Every attempted tool call is persisted: the ``tool_calls`` table captures the
structured call, and ``audit_logs`` captures the human-readable intent. Values
listed in a tool's ``redact`` tuple are scrubbed from parameters.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.tools.base import ToolContext
from database.models import AuditLog, ToolCall

logger = logging.getLogger(__name__)


def redact_parameters(parameters: dict[str, Any], redact: tuple[str, ...]) -> dict[str, Any]:
    if not redact:
        return parameters
    return {
        key: ("[redacted]" if key in redact else value) for key, value in parameters.items()
    }


async def record_tool_call(
    session: AsyncSession,
    *,
    context: ToolContext,
    tool_name: str,
    parameters: dict[str, Any],
    status: str,
    redact: tuple[str, ...] = (),
    error: str | None = None,
    duration_ms: int | None = None,
) -> ToolCall:
    """Insert a row into ``tool_calls`` and flush (no commit — caller owns it)."""
    call = ToolCall(
        conversation_id=context.conversation_id,
        device_id=context.device_id,
        tool=tool_name,
        parameters=redact_parameters(parameters, redact),
        status=status,
        duration_ms=duration_ms,
        error=error,
    )
    session.add(call)
    await session.flush()
    logger.info(
        "tool call recorded",
        extra={
            "tool": tool_name,
            "status": status,
            "conversation_id": str(context.conversation_id) if context.conversation_id else None,
            "duration_ms": duration_ms,
        },
    )
    return call


async def record_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    context: ToolContext,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        user_id=context.user_id,
        action=action,
        target=target,
        details=details,
    )
    session.add(entry)
    await session.flush()
    return entry
