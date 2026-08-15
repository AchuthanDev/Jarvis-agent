"""Device registry, device WebSocket, and command dispatch endpoints."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db, get_device_connections
from core.audit.record import record_audit, record_tool_call
from core.config import settings
from core.devices.auth import (
    generate_device_token,
    hash_device_token,
    verify_device_token,
)
from core.devices.manager import (
    DeviceCommandError,
    DeviceConnectionManager,
    DeviceOfflineError,
)
from core.devices.protocol import (
    normalize_windows_command,
    sanitized_parameters,
    validate_http_url,
)
from core.devices.service import list_devices, load_device, mark_device_seen, register_device
from core.tools.base import ToolContext
from database.models import Device

logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])


class DeviceRegisterRequest(BaseModel):
    registration_secret: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=128)
    device_type: str = Field(default="unknown", min_length=1, max_length=32)
    operating_system: str | None = Field(default=None, max_length=64)
    agent_version: str | None = Field(default=None, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class DeviceRegisterResponse(BaseModel):
    device_id: UUID
    device_token: str


class DeviceOut(BaseModel):
    id: UUID
    name: str
    device_type: str
    operating_system: str | None = None
    online: bool
    last_seen: datetime | None = None
    ip_address: str | None = None
    agent_version: str | None = None
    permission_level: int
    capabilities: list[str]


class DeviceCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout: float | None = Field(default=None, ge=1, le=120)


class DeviceCommandResponse(BaseModel):
    request_id: str
    device_id: UUID
    tool: str
    status: str
    result: dict[str, Any]
    error: str | None = None
    execution_time: float | None = None


def _device_out(device: Device, *, online_override: bool | None = None) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        device_type=device.device_type,
        operating_system=device.operating_system,
        online=device.online if online_override is None else online_override,
        last_seen=device.last_seen,
        ip_address=device.ip_address,
        agent_version=device.agent_version,
        permission_level=device.permission_level,
        capabilities=[cap.capability for cap in device.capabilities],
    )


def _require_admin_token(x_jarvis_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.direct_admin_token()
    if not expected or x_jarvis_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def _device_has_capability(device: Device, tool: str) -> bool:
    return any(cap.capability == tool for cap in device.capabilities)


def _validate_windows_parameters(tool: str, parameters: dict[str, Any]) -> None:
    if tool == "windows.open_url":
        url = parameters.get("url")
        if not isinstance(url, str):
            raise HTTPException(status_code=422, detail="parameters.url is required")
        try:
            validate_http_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/devices/register", response_model=DeviceRegisterResponse, status_code=201)
async def register(
    request: DeviceRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> DeviceRegisterResponse:
    if not settings.device_registration_secret:
        raise HTTPException(
            status_code=503,
            detail="Device registration is disabled. Set DEVICE_REGISTRATION_SECRET.",
        )
    if request.registration_secret != settings.device_registration_secret:
        raise HTTPException(status_code=403, detail="Invalid registration secret")

    token = generate_device_token()
    device = await register_device(
        session,
        name=request.name,
        device_type=request.device_type,
        operating_system=request.operating_system,
        agent_version=request.agent_version,
        token_hash=hash_device_token(token, settings.jarvis_secret_key),
        capabilities=request.capabilities,
    )
    logger.info(
        "device registered",
        extra={"device_id": str(device.id), "device_name": device.name},
    )
    return DeviceRegisterResponse(device_id=device.id, device_token=token)


@router.get("/api/devices", response_model=list[DeviceOut])
async def devices(
    session: AsyncSession = Depends(get_db),
    manager: DeviceConnectionManager = Depends(get_device_connections),
) -> list[DeviceOut]:
    return [
        _device_out(device, online_override=manager.is_online(device.id))
        for device in await list_devices(session)
    ]


@router.get("/api/devices/{device_id}", response_model=DeviceOut)
async def device(
    device_id: UUID,
    session: AsyncSession = Depends(get_db),
    manager: DeviceConnectionManager = Depends(get_device_connections),
) -> DeviceOut:
    loaded = await load_device(session, device_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return _device_out(loaded, online_override=manager.is_online(loaded.id))


@router.post("/api/devices/{device_id}/commands", response_model=DeviceCommandResponse)
async def command_device(
    device_id: UUID,
    request: DeviceCommandRequest,
    _: None = Depends(_require_admin_token),
    session: AsyncSession = Depends(get_db),
    manager: DeviceConnectionManager = Depends(get_device_connections),
) -> DeviceCommandResponse:
    device = await load_device(session, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.device_type != "windows":
        raise HTTPException(status_code=400, detail="Only Windows commands are supported")
    try:
        command = normalize_windows_command(request.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not _device_has_capability(device, command.tool):
        raise HTTPException(
            status_code=400,
            detail=f"Device does not advertise capability {command.tool}",
        )
    _validate_windows_parameters(command.tool, request.parameters)
    context = ToolContext(device_id=device_id)
    started = time.perf_counter()
    clean_parameters = sanitized_parameters(command.tool, request.parameters)
    try:
        raw = await manager.dispatch_raw(
            device_id,
            command.action,
            request.parameters,
            tool=command.tool,
            timeout=request.timeout,
        )
    except DeviceOfflineError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        await record_tool_call(
            session,
            context=context,
            tool_name=command.tool,
            parameters=clean_parameters,
            status="failed",
            error="Device is offline",
            duration_ms=duration_ms,
        )
        await record_audit(
            session,
            actor="api",
            action="device_command.failed",
            context=context,
            target=str(device_id),
            details={"tool": command.tool, "reason": "offline", "duration_ms": duration_ms},
        )
        await session.commit()
        raise HTTPException(status_code=409, detail="Device is offline") from exc
    except DeviceCommandError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        await record_tool_call(
            session,
            context=context,
            tool_name=command.tool,
            parameters=clean_parameters,
            status="failed",
            error=str(exc),
            duration_ms=duration_ms,
        )
        await record_audit(
            session,
            actor="api",
            action="device_command.failed",
            context=context,
            target=str(device_id),
            details={"tool": command.tool, "duration_ms": duration_ms},
        )
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = raw.get("result") if isinstance(raw.get("result"), dict) else {"value": raw.get("result")}
    await record_tool_call(
        session,
        context=context,
        tool_name=command.tool,
        parameters=clean_parameters,
        status="executed",
        duration_ms=duration_ms,
    )
    await record_audit(
        session,
        actor="api",
        action="device_command.executed",
        context=context,
        target=str(device_id),
        details={
            "request_id": raw["request_id"],
            "tool": command.tool,
            "duration_ms": duration_ms,
        },
    )
    await session.commit()
    return DeviceCommandResponse(
        request_id=raw["request_id"],
        device_id=device_id,
        tool=command.tool,
        status="executed",
        result=result,
        error=raw.get("error"),
        execution_time=raw.get("execution_time"),
    )


@router.websocket("/ws/device")
async def device_websocket(
    websocket: WebSocket,
    device_id: UUID = Query(),
    token: str = Query(min_length=1),
) -> None:
    sessionmaker = websocket.app.state.db_sessionmaker
    manager: DeviceConnectionManager = websocket.app.state.device_connections
    async with sessionmaker() as session:
        device = await load_device(session, device_id)
        if device is None or not verify_device_token(
            token, device.token_hash, settings.jarvis_secret_key
        ):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await manager.connect(device_id, websocket)
        await mark_device_seen(
            session,
            device=device,
            online=True,
            ip_address=websocket.client.host if websocket.client else None,
        )
        await websocket.send_json({"type": "connected", "device_id": str(device_id)})

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "heartbeat":
                await manager.mark_heartbeat(device_id)
                capabilities = message.get("capabilities")
                async with sessionmaker() as session:
                    device = await load_device(session, device_id)
                    if device is not None:
                        await mark_device_seen(
                            session,
                            device=device,
                            online=True,
                            capabilities=capabilities if isinstance(capabilities, list) else None,
                        )
                await websocket.send_json({"type": "heartbeat_ack"})
            elif message_type == "response":
                await manager.mark_heartbeat(device_id)
                await manager.handle_response(device_id, message)
            else:
                await websocket.send_json(
                    {"type": "error", "error": f"unsupported message type {message_type!r}"}
                )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(device_id, websocket)
        async with sessionmaker() as session:
            device = await load_device(session, device_id)
            if device is not None:
                await mark_device_seen(session, device=device, online=False)
