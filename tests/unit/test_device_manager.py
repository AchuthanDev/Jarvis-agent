"""Tests for the live device connection manager."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from core.devices.manager import DeviceCommandError, DeviceConnectionManager, DeviceOfflineError


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False

    async def send_text(self, message: str) -> None:
        await self.sent.put(message)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_dispatch_sends_command_and_waits_for_response() -> None:
    manager = DeviceConnectionManager(command_timeout=1)
    device_id = uuid4()
    websocket = FakeWebSocket()
    await manager.connect(device_id, websocket)

    task = asyncio.create_task(
        manager.dispatch(device_id, "open_url", {"url": "https://google.com"})
    )
    command = json.loads(await websocket.sent.get())
    assert command["type"] == "command"
    assert command["device_id"] == str(device_id)
    assert command["tool"] == "open_url"
    assert command["action"] == "open_url"
    assert command["parameters"] == {"url": "https://google.com"}
    assert "request_id" in command
    assert "timestamp" in command
    assert command["timeout"] == 1

    await manager.handle_response(
        device_id,
        {
            "type": "response",
            "request_id": command["request_id"],
            "success": True,
            "result": {"opened": True},
        },
    )

    assert await task == {"opened": True}


@pytest.mark.asyncio
async def test_dispatch_ignores_response_from_wrong_device() -> None:
    manager = DeviceConnectionManager(command_timeout=0.05)
    device_id = uuid4()
    other_device_id = uuid4()
    websocket = FakeWebSocket()
    await manager.connect(device_id, websocket)

    task = asyncio.create_task(manager.dispatch(device_id, "open_url", {}))
    command = json.loads(await websocket.sent.get())
    await manager.handle_response(
        device_id,
        {
            "type": "response",
            "request_id": command["request_id"],
            "device_id": str(other_device_id),
            "success": True,
            "result": {"opened": True},
        },
    )

    with pytest.raises(DeviceCommandError, match="timed out"):
        await task


@pytest.mark.asyncio
async def test_duplicate_device_connection_closes_previous() -> None:
    manager = DeviceConnectionManager(command_timeout=1)
    device_id = uuid4()
    first = FakeWebSocket()
    second = FakeWebSocket()

    await manager.connect(device_id, first)
    await manager.connect(device_id, second)

    assert first.closed is True
    assert manager.is_online(device_id) is True
    await manager.disconnect(device_id, first)
    assert manager.is_online(device_id) is True


@pytest.mark.asyncio
async def test_stale_connection_is_treated_as_offline() -> None:
    manager = DeviceConnectionManager(command_timeout=1, heartbeat_timeout=0.01)
    device_id = uuid4()
    websocket = FakeWebSocket()
    await manager.connect(device_id, websocket)
    await asyncio.sleep(0.02)

    assert manager.is_online(device_id) is False
    with pytest.raises(DeviceOfflineError):
        await manager.dispatch(device_id, "system_info", {})


@pytest.mark.asyncio
async def test_dispatch_raises_on_device_failure_response() -> None:
    manager = DeviceConnectionManager(command_timeout=1)
    device_id = uuid4()
    websocket = FakeWebSocket()
    await manager.connect(device_id, websocket)

    task = asyncio.create_task(manager.dispatch(device_id, "open_app", {"app": "x"}))
    command = json.loads(await websocket.sent.get())
    await manager.handle_response(
        device_id,
        {
            "type": "response",
            "request_id": command["request_id"],
            "success": False,
            "error": "not allowed",
        },
    )

    with pytest.raises(DeviceCommandError, match="not allowed"):
        await task
