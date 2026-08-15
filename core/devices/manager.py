"""In-process manager for currently connected device agents."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingCommand:
    future: asyncio.Future[dict[str, Any]]
    action: str
    tool: str
    started_at: float


@dataclass(slots=True)
class DeviceConnection:
    device_id: UUID
    websocket: WebSocket
    pending: dict[str, PendingCommand] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.monotonic)


class DeviceOfflineError(RuntimeError):
    """Device is not currently connected."""


class DeviceCommandError(RuntimeError):
    """Device command failed or timed out."""


class DeviceConnectionManager:
    def __init__(
        self,
        *,
        command_timeout: float = 20.0,
        heartbeat_timeout: float = 45.0,
    ) -> None:
        self._connections: dict[UUID, DeviceConnection] = {}
        self._command_timeout = command_timeout
        self._heartbeat_timeout = heartbeat_timeout
        self._lock = asyncio.Lock()

    async def connect(self, device_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            previous = self._connections.get(device_id)
            if previous is not None:
                await self._close_connection(previous)
            self._connections[device_id] = DeviceConnection(device_id, websocket)
        logger.info("device connected", extra={"device_id": str(device_id)})

    async def disconnect(self, device_id: UUID, websocket: WebSocket | None = None) -> None:
        async with self._lock:
            connection = self._connections.get(device_id)
            if connection is not None and websocket is not None and connection.websocket is not websocket:
                return
            if connection is not None:
                self._connections.pop(device_id, None)
        if connection is not None:
            for pending in connection.pending.values():
                if not pending.future.done():
                    pending.future.set_exception(DeviceOfflineError("device disconnected"))
            logger.info("device disconnected", extra={"device_id": str(device_id)})

    def is_online(self, device_id: UUID) -> bool:
        connection = self._connections.get(device_id)
        return connection is not None and not self._is_stale(connection)

    def online_device_ids(self) -> set[UUID]:
        return {
            device_id
            for device_id, connection in self._connections.items()
            if not self._is_stale(connection)
        }

    async def mark_heartbeat(self, device_id: UUID) -> None:
        connection = self._connections.get(device_id)
        if connection is not None:
            connection.last_heartbeat = time.monotonic()

    async def dispatch(
        self,
        device_id: UUID,
        action: str,
        parameters: dict[str, Any],
        *,
        tool: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        response = await self.dispatch_raw(
            device_id, action, parameters, timeout=timeout, tool=tool or action
        )
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    async def dispatch_raw(
        self,
        device_id: UUID,
        action: str,
        parameters: dict[str, Any],
        *,
        tool: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        connection = self._connections.get(device_id)
        if connection is None or self._is_stale(connection):
            raise DeviceOfflineError("device is offline")

        request_id = str(uuid4())
        command_timeout = timeout or self._command_timeout
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        connection.pending[request_id] = PendingCommand(
            future=future,
            action=action,
            tool=tool,
            started_at=time.perf_counter(),
        )
        message = {
            "type": "command",
            "request_id": request_id,
            "device_id": str(device_id),
            "tool": tool,
            "action": action,
            "parameters": parameters,
            "timestamp": datetime.now(UTC).isoformat(),
            "timeout": command_timeout,
        }
        try:
            await connection.websocket.send_text(json.dumps(message))
            response = await asyncio.wait_for(future, timeout=command_timeout)
        except asyncio.TimeoutError as exc:
            raise DeviceCommandError(
                f"device command timed out after {command_timeout:.0f}s"
            ) from exc
        finally:
            connection.pending.pop(request_id, None)

        if not response.get("success"):
            error = response.get("error") or "device command failed"
            raise DeviceCommandError(str(error))
        response.setdefault("request_id", request_id)
        response.setdefault("error", None)
        response.setdefault("execution_time", None)
        return response

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
        if message.get("device_id") not in {None, str(device_id)}:
            logger.warning(
                "ignoring device response with mismatched device id",
                extra={"device_id": str(device_id), "request_id": request_id},
            )
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

    def _is_stale(self, connection: DeviceConnection) -> bool:
        return (time.monotonic() - connection.last_heartbeat) > self._heartbeat_timeout
