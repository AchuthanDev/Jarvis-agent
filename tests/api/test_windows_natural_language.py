"""Natural-language Windows control through the chat agent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from core.devices.manager import DeviceCommandError, DeviceOfflineError
from core.llm.base import LLMProvider
from core.llm.types import ChatMessage, LLMResponse
from database.models import Device, DeviceCapability

CAPABILITIES = [
    "windows.open_url",
    "windows.open_app",
    "windows.notification",
    "windows.system_info",
]


class WindowsIntentProvider(LLMProvider):
    name = "windows-intent-fake"
    model = "windows-intent-fake-model"

    def __init__(self, first_tool: str, final_reply: str) -> None:
        self.first_tool = first_tool
        self.final_reply = final_reply
        self.calls = 0

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        del messages, temperature, max_tokens
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(content=self.first_tool)
        return LLMResponse(content=self.final_reply)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        del messages, temperature, max_tokens
        yield self.final_reply


class FakeDeviceManager:
    def __init__(self, *, mode: str = "ok") -> None:
        self.mode = mode
        self.calls: list[tuple[Any, str, dict[str, Any], str | None]] = []
        self.online_ids: set[Any] = set()

    def online_device_ids(self) -> set[Any]:
        return self.online_ids

    async def dispatch(
        self,
        device_id,
        action: str,
        parameters: dict[str, Any],
        *,
        tool: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        del timeout
        self.calls.append((device_id, action, parameters, tool))
        if self.mode == "offline":
            raise DeviceOfflineError("device is offline")
        if self.mode == "timeout":
            raise DeviceCommandError("device command timed out after 20s")
        if self.mode == "failure":
            raise DeviceCommandError("I do not know how to open that application yet")
        if action == "system_info":
            return {
                "hostname": "Friday",
                "ram_total_bytes": 16_000_000_000,
                "ram_used_bytes": 10_400_000_000,
                "ram_percent": 65.0,
                "cpu_usage_percent": 18.0,
                "battery_percent": 72,
                "disk_total_bytes": 500_000_000_000,
                "disk_used_bytes": 350_000_000_000,
                "disk_percent": 70.0,
                "local_ip": "192.168.1.3",
                "uptime_seconds": 3600,
            }
        return {"ok": True, **parameters}


def _client(sessionmaker, provider: LLMProvider, manager: FakeDeviceManager) -> TestClient:
    from apps.api.deps import get_db, get_device_connections, get_llm
    from apps.api.main import create_app

    app = create_app()

    async def override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: provider
    app.dependency_overrides[get_device_connections] = lambda: manager
    return TestClient(app)


async def _create_windows_device(sessionmaker, *, name: str = "My-Laptop") -> UUID:
    async with sessionmaker() as session:
        device = Device(name=name, device_type="windows")
        session.add(device)
        await session.flush()
        for capability in CAPABILITIES:
            session.add(DeviceCapability(device_id=device.id, capability=capability))
        await session.commit()
        return device.id


@pytest.mark.parametrize(
    ("message", "tool_json", "expected_action", "expected_parameters", "reply"),
    [
        (
            "Open Google on my laptop.",
            '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","url":"Google"}}',
            "open_url",
            {"url": "https://www.google.com"},
            "Google is open on your laptop.",
        ),
        (
            "Open VS Code.",
            '{"tool":"windows.open_app","arguments":{"app":"vscode"}}',
            "open_app",
            {"app": "vscode"},
            "VS Code is open.",
        ),
        (
            "Open Chrome.",
            '{"tool":"windows.open_app","arguments":{"app":"chrome"}}',
            "open_app",
            {"app": "chrome"},
            "Chrome is open.",
        ),
        (
            "Open YouTube on my laptop.",
            '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","url":"YouTube"}}',
            "open_url",
            {"url": "https://www.youtube.com"},
            "YouTube is open on your laptop.",
        ),
        (
            "Search Google for test query on my laptop.",
            '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","search_query":"test query"}}',
            "open_url",
            {"url": "https://www.google.com/search?q=test+query"},
            "I opened the Google search on your laptop.",
        ),
    ],
)
def test_natural_language_windows_actions(
    sessionmaker,
    message: str,
    tool_json: str,
    expected_action: str,
    expected_parameters: dict[str, Any],
    reply: str,
) -> None:
    device_id = asyncio.run(_create_windows_device(sessionmaker))
    manager = FakeDeviceManager()
    manager.online_ids = {device_id}
    provider = WindowsIntentProvider(tool_json, reply)

    with _client(sessionmaker, provider, manager) as client:
        response = client.post("/api/chat", json={"message": message})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == reply
    assert body["message"] == reply
    assert body["tool_calls"][0]["tool"] in {"windows.open_url", "windows.open_app"}
    assert manager.calls[0][1] == expected_action
    assert manager.calls[0][2] == expected_parameters


@pytest.mark.parametrize(
    ("message", "tool_json", "reply"),
    [
        (
            "How much RAM is my laptop using?",
            '{"tool":"windows.system_info","arguments":{"device_name":"my laptop"}}',
            "Your laptop is using 10.4 GB of 16.0 GB RAM, about 65%.",
        ),
        (
            "What's my battery level?",
            '{"tool":"windows.system_info","arguments":{"device_name":"my laptop"}}',
            "Your laptop battery is at 72%.",
        ),
        (
            "What about CPU?",
            '{"tool":"windows.system_info","arguments":{"device_name":"my laptop"}}',
            "CPU usage is currently 18%.",
        ),
    ],
)
def test_natural_language_system_info(
    sessionmaker,
    message: str,
    tool_json: str,
    reply: str,
) -> None:
    device_id = asyncio.run(_create_windows_device(sessionmaker))
    manager = FakeDeviceManager()
    manager.online_ids = {device_id}
    provider = WindowsIntentProvider(tool_json, reply)

    with _client(sessionmaker, provider, manager) as client:
        response = client.post("/api/chat", json={"message": message})

    assert response.status_code == 200
    assert response.json()["reply"] == reply
    assert manager.calls[0][1] == "system_info"


@pytest.mark.parametrize(
    ("mode", "tool_json", "reply"),
    [
        (
            "offline",
            '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","url":"Google"}}',
            "I can't reach your laptop right now.",
        ),
        (
            "timeout",
            '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","url":"Google"}}',
            "I sent the command, but your laptop didn't respond.",
        ),
        (
            "failure",
            '{"tool":"windows.open_app","arguments":{"app":"unknown-app"}}',
            "I don't know how to open that application yet.",
        ),
    ],
)
def test_natural_language_windows_failures(
    sessionmaker,
    mode: str,
    tool_json: str,
    reply: str,
) -> None:
    device_id = asyncio.run(_create_windows_device(sessionmaker))
    manager = FakeDeviceManager(mode=mode)
    manager.online_ids = {device_id}
    provider = WindowsIntentProvider(tool_json, reply)

    with _client(sessionmaker, provider, manager) as client:
        response = client.post("/api/chat", json={"message": "Do the thing."})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == reply
    assert body["tool_calls"][0]["status"] == "failed"


def test_natural_language_invalid_url_is_not_dispatched(sessionmaker) -> None:
    device_id = asyncio.run(_create_windows_device(sessionmaker))
    manager = FakeDeviceManager()
    manager.online_ids = {device_id}
    provider = WindowsIntentProvider(
        '{"tool":"windows.open_url","arguments":{"device_name":"my laptop","url":"file:///C:/Windows"}}',
        "That URL is not allowed. I can only open http or https links.",
    )

    with _client(sessionmaker, provider, manager) as client:
        response = client.post("/api/chat", json={"message": "Open file URL."})

    assert response.status_code == 200
    assert response.json()["tool_calls"][0]["status"] == "failed"
    assert manager.calls == []


def test_multiple_windows_devices_returns_clarification(sessionmaker) -> None:
    asyncio.run(_create_windows_device(sessionmaker, name="Laptop-One"))
    asyncio.run(_create_windows_device(sessionmaker, name="Laptop-Two"))
    manager = FakeDeviceManager()
    provider = WindowsIntentProvider(
        '{"tool":"windows.system_info","arguments":{}}',
        "Which laptop do you mean?",
    )

    with _client(sessionmaker, provider, manager) as client:
        response = client.post("/api/chat", json={"message": "How much RAM is my laptop using?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Which laptop do you mean?"
    assert response.json()["tool_calls"][0]["status"] == "failed"
