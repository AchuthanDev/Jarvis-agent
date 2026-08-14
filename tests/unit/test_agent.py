"""Tests for the agent loop and JSON tool-request parsing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest

from core.agent import MAX_TOOL_ITERATIONS, format_result_for_model, parse_tool_request
from core.agent.loop import run_agent_turn
from core.agent.parsing import ToolRequest
from core.llm.base import LLMProvider
from core.llm.types import ChatMessage, LLMResponse
from core.security.permissions import PermissionPolicy
from core.tools.base import RISK_APPROVAL, RISK_READ_ONLY, Tool, ToolContext
from core.tools.builtins.time_tool import current_time_tool
from core.tools.registry import ToolRegistry


class ScriptedProvider(LLMProvider):
    name = "scripted"
    model = "scripted-model"

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        content = self._replies.pop(0) if self._replies else "Final answer."
        return LLMResponse(content=content)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield "streamed"


# --- parsing ---


def test_parse_rejects_prose() -> None:
    assert parse_tool_request("The time is 12:00.") is None


def test_parse_accepts_plain_json() -> None:
    request = parse_tool_request('{"tool": "current_time", "arguments": {}}')
    assert request == ToolRequest(name="current_time", arguments={})


def test_parse_accepts_fenced_json() -> None:
    request = parse_tool_request('```json\n{"tool": "current_time", "arguments": {"tz": "UTC"}}\n```')
    assert request == ToolRequest(name="current_time", arguments={"tz": "UTC"})


def test_parse_ignores_trailing_prose() -> None:
    request = parse_tool_request('{"tool": "current_time", "arguments": {}}  here is more')
    assert request is not None
    assert request.name == "current_time"


def test_parse_rejects_json_embedded_in_prose() -> None:
    assert parse_tool_request('The answer is {"tool": "current_time"}.') is None


def test_parse_rejects_object_without_tool_key() -> None:
    assert parse_tool_request('{"answer": "42"}') is None


def test_parse_defaults_missing_arguments() -> None:
    request = parse_tool_request('{"tool": "web.search"}')
    assert request is not None
    assert request.arguments == {}


# --- tool result formatting ---


def test_format_executed_result() -> None:
    from core.tools.base import ToolResult

    result = ToolResult(name="current_time", arguments={}, status="executed", output="12:00")
    assert "12:00" in format_result_for_model(result)


def test_format_denied_result() -> None:
    from core.tools.base import ToolResult

    result = ToolResult(
        name="server.system_status",
        arguments={},
        status="denied",
        denied_reason="risk too high",
    )
    assert "denied" in format_result_for_model(result)


# --- agent loop ---


def _registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


@pytest.mark.asyncio
async def test_loop_executes_tool_then_answers() -> None:
    provider = ScriptedProvider(
        '{"tool": "current_time", "arguments": {}}', "The time is stored above."
    )
    result = await run_agent_turn(
        provider,
        _registry(current_time_tool()),
        PermissionPolicy(),
        [ChatMessage(role="user", content="What time is it?")],
        context=ToolContext(),
    )

    assert result.reply == "The time is stored above."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].status == "executed"
    assert "It is" in result.tool_calls[0].output
    assert len(provider.calls) == 2
    # The tool result was appended as a user observation.
    assert "result:" in provider.calls[1][-1].content


@pytest.mark.asyncio
async def test_loop_denies_high_risk_tool() -> None:
    async def sensitive_op(*, context: ToolContext) -> str:
        del context
        return "done"

    sensitive = Tool(
        name="sensitive.op",
        description="requires approval",
        parameters={},
        fn=sensitive_op,
        risk=RISK_APPROVAL,
    )
    provider = ScriptedProvider('{"tool": "sensitive.op", "arguments": {}}', "Can't do that.")
    result = await run_agent_turn(
        provider,
        _registry(sensitive),
        PermissionPolicy(max_autonomous_risk=0),
        [ChatMessage(role="user", content="Do the op")],
        context=ToolContext(),
    )

    assert result.tool_calls[0].status == "denied"
    assert result.reply == "Can't do that."
    assert "denied" in provider.calls[1][-1].content


@pytest.mark.asyncio
async def test_loop_reports_unknown_tool() -> None:
    provider = ScriptedProvider('{"tool": "nope.missing", "arguments": {}}', "No such tool.")
    result = await run_agent_turn(
        provider,
        _registry(current_time_tool()),
        PermissionPolicy(),
        [ChatMessage(role="user", content="hi")],
        context=ToolContext(),
    )

    assert result.tool_calls[0].status == "not_found"
    assert "does not exist" in provider.calls[1][-1].content


@pytest.mark.asyncio
async def test_loop_stops_after_iteration_budget() -> None:
    provider = ScriptedProvider(
        *['{"tool": "current_time", "arguments": {}}'] * MAX_TOOL_ITERATIONS
    )
    result = await run_agent_turn(
        provider,
        _registry(current_time_tool()),
        PermissionPolicy(),
        [ChatMessage(role="user", content="hi")],
        context=ToolContext(),
    )

    assert len(result.tool_calls) == MAX_TOOL_ITERATIONS
    assert "limit" in result.reply


@pytest.mark.asyncio
async def test_loop_catches_failing_tool() -> None:
    async def explode(*, context: ToolContext) -> str:
        del context
        raise RuntimeError("kaboom")

    broken = Tool(
        name="broken.op",
        description="always fails",
        parameters={},
        fn=explode,
        risk=RISK_READ_ONLY,
    )
    provider = ScriptedProvider('{"tool": "broken.op", "arguments": {}}', "It broke.")
    result = await run_agent_turn(
        provider,
        _registry(broken),
        PermissionPolicy(),
        [ChatMessage(role="user", content="hi")],
        context=ToolContext(),
    )

    assert result.tool_calls[0].status == "failed"
    assert "kaboom" in result.tool_calls[0].error
    assert result.reply == "It broke."
