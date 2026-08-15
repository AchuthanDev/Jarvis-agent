"""In-process manager for currently connected device agents."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingCommand:
    future: asyncio.Future[dict[str, Any]]
    action: str


@dataclass(slots=True)
class DeviceConnection:
    device_id: UUID
    websocket: WebSocket
    pending: dict[str, PendingCommand] = field(default_factory=dict)


class DeviceOfflineError(RuntimeError):
    """Device is not currently connected."""


class DeviceCommandError(RuntimeError):
    """Device command failed or timed out."""


class DeviceConnectionManager:
    def __init__(self, *, command_timeout: float = 20.0) -> None:
        self._connections: dict[UUID, DeviceConnection] = {}
        self._command_timeout = command_timeout
        self._lock = asyncio.Lock()

    async def connect(self, device_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            previous = self._connections.get(device_id)
            if previous is not None:
                await self._close_connection(previous)
            self._connections[device_id] = DeviceConnection(device_id, websocket)
        logger.info("device connected", extra={"device_id": str(device_id)})

    async def disconnect(self, device_id: UUID) -> None:
        async with self._lock:
            connection = self._connections.pop(device_id, None)
        if connection is not None:
            for pending in connection.pending.values():
                if not pending.future.done():
                    pending.future.set_exception(DeviceOfflineError("device disconnected"))
            logger.info("device disconnected", extra={"device_id": str(device_id)})

    def is_online(self, device_id: UUID) -> bool:
        return device_id in self._connections

    def online_device_ids(self) -> set[UUID]:
        return set(self._connections)

    async def dispatch(
        self,
        device_id: UUID,
        action: str,
        parameters: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        connection = self._connections.get(device_id)
        if connection is None:
            raise DeviceOfflineError("device is offline")

        request_id = str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        connection.pending[request_id] = PendingCommand(future=future, action=action)
        message = {
            "type": "command",
            "request_id": request_id,
            "action": action,
            "parameters": parameters,
        }
        try:
            await connection.websocket.send_text(json.dumps(message))
            response = await asyncio.wait_for(
                future, timeout=timeout or self._command_timeout
            )
        except TimeoutError as exc:
            raise DeviceCommandError(f"device command timed out after {timeout or self._command_timeout:.0f}s") from exc
        finally:
            connection.pending.pop(request_id, None)

        if not response.get("success"):
            error = response.get("error") or "device command failed"
            raise DeviceCommandError(str(error))
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    async def handle_response(self, device_id: UUID, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        if not isinstance(request_id, str):
            return
        connection = self._connections.get(device_id)
        if connection is None:
            return
        pending = connection.pending.get(request_id)
        if pending is None or pending.future.done():
            return
        pending.future.set_result(message)

    async def close_all(self) -> None:
        async with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for connection in connections:
            await self._close_connection(connection)

    @staticmethod
    async def _close_connection(connection: DeviceConnection) -> None:
        for pending in connection.pending.values():
            if not pending.future.done():
                pending.future.set_exception(DeviceOfflineError("device disconnected"))
        await connection.websocket.close()
