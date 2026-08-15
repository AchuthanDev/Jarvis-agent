"""Tests for the live device connection manager."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from core.devices.manager import DeviceCommandError, DeviceConnectionManager


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
    assert command["action"] == "open_url"
    assert command["parameters"] == {"url": "https://google.com"}

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
