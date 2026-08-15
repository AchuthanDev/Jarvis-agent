"""Tests for the tool registry, validation and built-in tools."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
import pytest

from core.tools.base import RISK_APPROVAL, RISK_READ_ONLY, Tool, ToolContext
from core.tools.builtins import register_default_tools
from core.tools.builtins.system_status import system_status_tool
from core.tools.builtins.time_tool import current_time_tool
from core.tools.builtins.web_search import web_search_tool
from core.tools.registry import ToolRegistry
from core.tools.validation import ToolValidationError

EXPECTED_DEFAULT_TOOLS = {
    "current_time",
    "devices.list",
    "server.system_status",
    "memory.remember",
    "memory.recall",
    "web.search",
    "windows.notification",
    "windows.open_app",
    "windows.open_url",
    "windows.system_info",
}


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry


def test_default_tools_registered() -> None:
    registry = _registry()
    assert set(registry.names()) == EXPECTED_DEFAULT_TOOLS


def test_registry_rejects_duplicates() -> None:
    registry = _registry()
    with pytest.raises(ValueError):
        registry.register(current_time_tool())


def test_tool_without_description_rejected() -> None:
    with pytest.raises(ValueError):
        Tool(name="x", description="", parameters={}, fn=async_fn)


async def async_fn(*, context: ToolContext) -> str:
    del context
    return "ok"


def test_validation_rejects_unexpected_arguments() -> None:
    tool = current_time_tool()
    with pytest.raises(ToolValidationError):
        asyncio.run(tool.run({"bogus": 1}, ToolContext()))


def test_validation_rejects_wrong_type() -> None:
    tool = web_search_tool()
    with pytest.raises(ToolValidationError):
        asyncio.run(tool.run({"query": 42}, ToolContext()))


def test_current_time() -> None:
    result = asyncio.run(current_time_tool().run({}, ToolContext()))
    assert "It is" in result
    datetime.fromisoformat(result.split("(")[0].replace("It is ", "").strip())


def test_system_status() -> None:
    result = asyncio.run(system_status_tool().run({}, ToolContext()))
    assert isinstance(result, dict)
    assert result["hostname"]
    assert "cpu_percent" in result
    assert "memory_percent" in result
    assert "uptime_seconds" in result
    assert 0 <= result["cpu_percent"] <= 100


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, *, response: str, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, data: dict[str, str]) -> _FakeResponse:
        del url, data
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._response)


_HTML_SAMPLE = """\
<a class="result__a" href="https://example.com/1">Example Title</a>
<a class="result__snippet">Snippet one.</a>
<a class="result__a" href="https://example.com/2">Second &amp; Title</a>
<a class="result__snippet">Snippet <b>two</b>.</a>
"""


def test_web_search_strips_html_and_returns_results(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.tools.builtins.web_search.httpx.AsyncClient",
        lambda **kwargs: _FakeClient(response=_HTML_SAMPLE),
    )
    result = asyncio.run(
        web_search_tool().run({"query": "test", "max_results": 2}, ToolContext())
    )
    assert result["query"] == "test"
    assert [r["title"] for r in result["results"]] == ["Example Title", "Second & Title"]
    assert result["results"][1]["snippet"] == "Snippet two."


def test_web_search_returns_error_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.tools.builtins.web_search.httpx.AsyncClient",
        lambda **kwargs: _FakeClient(response="", error=httpx.ConnectError("boom")),
    )
    result = asyncio.run(web_search_tool().run({"query": "test"}, ToolContext()))
    assert result["results"] == []
    assert "search failed" in result["error"]


def test_tool_describe_contains_name_and_risk() -> None:
    tool = current_time_tool()
    assert tool.name in tool.describe()


def test_risks_ordered_read_only_is_lowest() -> None:
    assert RISK_READ_ONLY < RISK_APPROVAL
