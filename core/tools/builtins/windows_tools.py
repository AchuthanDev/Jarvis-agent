"""Windows companion tools.

The central server never automates a desktop directly. These tools dispatch
validated, allowlisted commands to an authenticated Windows companion agent.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import settings
from core.devices.manager import DeviceCommandError, DeviceOfflineError
from core.devices.protocol import (
    normalize_windows_command,
    validate_http_url,
)
from core.tools.base import RISK_READ_ONLY, RISK_SAFE, Tool, ToolContext, ToolExecutionError
from database.models import Device


async def _device_by_id_or_name(context: ToolContext, value: str) -> Device | None:
    try:
        device_id = UUID(value)
        return (
            await context.session.scalars(
                select(Device)
                .options(selectinload(Device.capabilities))
                .where(Device.id == device_id)
                .limit(1)
            )
        ).first()
    except ValueError:
        return (
            await context.session.scalars(
                select(Device)
                .options(selectinload(Device.capabilities))
                .where(Device.name.ilike(value))
                .limit(1)
            )
        ).first()


async def _resolve_windows_device(
    context: ToolContext,
    *,
    device_id: str | None = None,
    device_name: str | None = None,
) -> Device:
    if context.session is None:
        raise ToolExecutionError("device tools require a database session")
    alias_map = settings.windows_alias_map()
    if device_id:
        device = await _device_by_id_or_name(context, device_id)
        if device is None:
            raise ToolExecutionError("Windows device not found")
    elif device_name:
        target = alias_map.get(device_name.strip().lower(), device_name)
        device = await _device_by_id_or_name(context, target)
    elif settings.default_windows_device:
        device = await _device_by_id_or_name(context, settings.default_windows_device)
    else:
        devices = list(
            (
                await context.session.scalars(
                    select(Device)
                    .options(selectinload(Device.capabilities))
                    .where(Device.device_type == "windows")
                    .order_by(Device.last_seen.desc().nulls_last())
                    .limit(2)
                )
            ).all()
        )
        if len(devices) == 1:
            device = devices[0]
        elif not devices:
            raise ToolExecutionError("no Windows devices are registered")
        else:
            names = ", ".join(d.name for d in devices)
            raise ToolExecutionError(f"multiple Windows devices match; specify one: {names}")

    if device is None:
        raise ToolExecutionError("Windows device not found")
    if device.device_type != "windows":
        raise ToolExecutionError(f"device {device.name!r} is not a Windows device")
    return device


def _ensure_capability(device: Device, tool: str) -> None:
    if not any(cap.capability == tool for cap in device.capabilities):
        raise ToolExecutionError(f"{device.name} does not support {tool}")


async def _dispatch(
    action: str,
    parameters: dict[str, Any],
    *,
    context: ToolContext,
    device_id: str | None = None,
    device_name: str | None = None,
) -> dict[str, Any]:
    if context.device_manager is None:
        raise ToolExecutionError("device connection manager is unavailable")
    command = normalize_windows_command(action)
    device = await _resolve_windows_device(
        context, device_id=device_id, device_name=device_name
    )
    _ensure_capability(device, command.tool)
    try:
        result = await context.device_manager.dispatch(
            device.id,
            command.action,
            parameters,
            tool=command.tool,
        )
    except DeviceOfflineError as exc:
        raise ToolExecutionError(f"{device.name} is offline") from exc
    except DeviceCommandError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"device_id": str(device.id), "device_name": device.name, **result}


async def _list_devices(*, context: ToolContext) -> dict[str, Any]:
    if context.session is None:
        raise ToolExecutionError("devices.list requires a database session")
    devices = list((await context.session.scalars(select(Device).order_by(Device.name))).all())
    online_ids = (
        context.device_manager.online_device_ids() if context.device_manager is not None else set()
    )
    return {
        "devices": [
            {
                "id": str(device.id),
                "name": device.name,
                "type": device.device_type,
                "operating_system": device.operating_system,
                "online": device.id in online_ids,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            }
            for device in devices
        ]
    }


async def _open_url(
    url: str,
    device_id: str | None = None,
    device_name: str | None = None,
    *,
    context: ToolContext,
) -> dict[str, Any]:
    try:
        validate_http_url(url)
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return await _dispatch(
        "open_url",
        {"url": url},
        context=context,
        device_id=device_id,
        device_name=device_name,
    )


async def _open_app(
    app: str,
    device_id: str | None = None,
    device_name: str | None = None,
    *,
    context: ToolContext,
) -> dict[str, Any]:
    return await _dispatch(
        "open_app",
        {"app": app},
        context=context,
        device_id=device_id,
        device_name=device_name,
    )


async def _notification(
    title: str,
    message: str,
    device_id: str | None = None,
    device_name: str | None = None,
    *,
    context: ToolContext,
) -> dict[str, Any]:
    return await _dispatch(
        "notification",
        {"title": title, "message": message},
        context=context,
        device_id=device_id,
        device_name=device_name,
    )


async def _system_info(
    device_id: str | None = None,
    device_name: str | None = None,
    *,
    context: ToolContext,
) -> dict[str, Any]:
    return await _dispatch(
        "system_info",
        {},
        context=context,
        device_id=device_id,
        device_name=device_name,
    )


_DEVICE_SELECTOR = {
    "device_id": {
        "type": "string",
        "description": "Optional registered device UUID. Use when known.",
    },
    "device_name": {
        "type": "string",
        "description": "Optional registered device name, e.g. Achuthan-Laptop.",
    },
}


def build_windows_tools() -> list[Tool]:
    return [
        Tool(
            name="devices.list",
            description="List registered devices and whether they are currently online.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            fn=_list_devices,
            risk=RISK_READ_ONLY,
            timeout=10.0,
        ),
        Tool(
            name="windows.open_url",
            description="Open a URL on a registered Windows companion device.",
            parameters={
                "type": "object",
                "properties": {
                    **_DEVICE_SELECTOR,
                    "url": {"type": "string", "format": "uri", "minLength": 1},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            fn=_open_url,
            risk=RISK_SAFE,
            timeout=20.0,
        ),
        Tool(
            name="windows.open_app",
            description="Open an installed application on a registered Windows device.",
            parameters={
                "type": "object",
                "properties": {
                    **_DEVICE_SELECTOR,
                    "app": {"type": "string", "minLength": 1},
                },
                "required": ["app"],
                "additionalProperties": False,
            },
            fn=_open_app,
            risk=RISK_SAFE,
            timeout=20.0,
        ),
        Tool(
            name="windows.notification",
            description="Show a notification on a registered Windows device.",
            parameters={
                "type": "object",
                "properties": {
                    **_DEVICE_SELECTOR,
                    "title": {"type": "string", "minLength": 1, "maxLength": 80},
                    "message": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                "required": ["title", "message"],
                "additionalProperties": False,
            },
            fn=_notification,
            risk=RISK_SAFE,
            timeout=20.0,
        ),
        Tool(
            name="windows.system_info",
            description="Get basic system information from a registered Windows device.",
            parameters={
                "type": "object",
                "properties": _DEVICE_SELECTOR,
                "additionalProperties": False,
            },
            fn=_system_info,
            risk=RISK_READ_ONLY,
            timeout=20.0,
        ),
    ]
