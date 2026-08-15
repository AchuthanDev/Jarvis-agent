"""The tool-using agent loop.

Plan: understand the user's request → decide whether a tool is needed → request
it as JSON → the loop executes it (subject to permission checks and audit
recording) → the result is fed back as a user-turn observation → the model
continues until it produces a natural-language reply or the iteration budget is
exhausted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from core.agent.parsing import ToolRequest, parse_tool_request
from core.audit.record import record_audit, record_tool_call
from core.llm.base import LLMProvider
from core.llm.types import ChatMessage
from core.security.permissions import PermissionPolicy
from core.tools.base import ToolContext, ToolExecutionError, ToolResult
from core.tools.registry import ToolRegistry
from core.tools.validation import ToolValidationError

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5


@dataclass(frozen=True, slots=True)
class AgentResult:
    reply: str
    tool_calls: list[ToolResult]


def _serialize(output: Any) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def format_result_for_model(result: ToolResult) -> str:
    if result.status == "executed":
        return (
            f"Tool '{result.name}' executed successfully. result: {result.output}\n"
            "Reply to the user in one short natural sentence. Do not dump raw JSON "
            "unless the user explicitly asked for raw output."
        )
    if result.status == "denied":
        return (
            f"Tool '{result.name}' was denied: {result.denied_reason}. "
            "Answer without it."
        )
    if result.status == "validation_error":
        return (
            f"Tool '{result.name}' rejected its arguments: {result.error}. "
            "Fix the arguments or answer without the tool."
        )
    if result.status == "not_found":
        return (
            f"Tool '{result.name}' does not exist. Choose a tool from the "
            "list or answer without one."
        )
    return (
        f"Tool '{result.name}' failed: {result.error}. "
        "Give the user a short natural explanation. If this was a Windows device "
        "action, do not claim success."
    )


async def _execute(
    request: ToolRequest,
    *,
    registry: ToolRegistry,
    policy: PermissionPolicy,
    context: ToolContext,
) -> ToolResult:
    started = time.perf_counter()
    tool = registry.get(request.name)
    if tool is None:
        return ToolResult(
            name=request.name,
            arguments=request.arguments,
            status="not_found",
            error=f"tool '{request.name}' is not registered",
        )

    decision = await policy.decide(context.session, context, tool.name, tool.risk)
    if not decision.allowed:
        if context.session is not None:
            await record_tool_call(
                context.session,
                context=context,
                tool_name=tool.name,
                parameters=request.arguments,
                status="denied",
                redact=tool.redact,
                error=decision.reason,
            )
            await record_audit(
                context.session,
                actor="llm",
                action="tool.denied",
                context=context,
                target=tool.name,
                details={"reason": decision.reason},
            )
        return ToolResult(
            name=tool.name,
            arguments=request.arguments,
            status="denied",
            denied_reason=decision.reason,
        )

    try:
        output = await asyncio.wait_for(
            tool.run(request.arguments, context), timeout=tool.timeout
        )
        status = "executed"
        error = None
    except ToolValidationError as exc:
        status = "validation_error"
        error = str(exc)
        output = None
    except ToolExecutionError as exc:
        status = "failed"
        error = str(exc)
        output = None
    except asyncio.TimeoutError:
        status = "failed"
        error = f"tool exceeded {tool.timeout:.0f}s timeout"
        output = None
    except Exception as exc:  # noqa: BLE001 — never let a tool break the loop
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        output = None

    duration_ms = int((time.perf_counter() - started) * 1000)
    if context.session is not None:
        await record_tool_call(
            context.session,
            context=context,
            tool_name=tool.name,
            parameters=request.arguments,
            status=status,
            redact=tool.redact,
            error=error,
            duration_ms=duration_ms,
        )
        await record_audit(
            context.session,
            actor="llm",
            action=f"tool.{status}",
            context=context,
            target=tool.name,
            details={"duration_ms": duration_ms},
        )
    logger.info(
        "tool executed",
        extra={
            "tool": tool.name,
            "status": status,
            "duration_ms": duration_ms,
        },
    )
    return ToolResult(
        name=tool.name,
        arguments=request.arguments,
        status=status,
        output=_serialize(output) if status == "executed" else None,
        error=error,
        duration_ms=duration_ms,
    )


async def run_agent_turn(
    provider: LLMProvider,
    registry: ToolRegistry,
    policy: PermissionPolicy,
    messages: list[ChatMessage],
    *,
    context: ToolContext,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> AgentResult:
    """Run one assistant turn, executing tools until the model replies in prose."""
    pending = list(messages)
    tool_calls: list[ToolResult] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await provider.chat(
            pending, temperature=temperature, max_tokens=max_tokens
        )
        request = parse_tool_request(response.content)
        if request is None:
            return AgentResult(reply=response.content, tool_calls=tool_calls)

        result = await _execute(request, registry=registry, policy=policy, context=context)
        tool_calls.append(result)
        if context.session is not None:
            await context.session.commit()
        pending.append(
            ChatMessage(role="user", content=format_result_for_model(result))
        )

    return AgentResult(
        reply=(
            "I ran into my limit of tool calls for this turn and couldn't "
            "finish. Please try a more specific request."
        ),
        tool_calls=tool_calls,
    )
