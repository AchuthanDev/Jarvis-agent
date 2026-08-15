"""Database operations for registered devices."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Device, DeviceCapability


async def set_device_capabilities(
    session: AsyncSession,
    *,
    device: Device,
    capabilities: list[str],
) -> None:
    unique = sorted({cap.strip() for cap in capabilities if cap.strip()})
    await session.execute(
        delete(DeviceCapability).where(DeviceCapability.device_id == device.id)
    )
    for capability in unique:
        session.add(DeviceCapability(device_id=device.id, capability=capability))


async def register_device(
    session: AsyncSession,
    *,
    name: str,
    device_type: str,
    operating_system: str | None,
    agent_version: str | None,
    token_hash: str,
    capabilities: list[str],
) -> Device:
    device = Device(
        name=name,
        device_type=device_type,
        operating_system=operating_system,
        agent_version=agent_version,
        token_hash=token_hash,
        online=False,
    )
    session.add(device)
    await session.flush()
    await set_device_capabilities(session, device=device, capabilities=capabilities)
    await session.commit()
    await session.refresh(device, attribute_names=["capabilities"])
    return device


async def mark_device_seen(
    session: AsyncSession,
    *,
    device: Device,
    online: bool,
    ip_address: str | None = None,
    capabilities: list[str] | None = None,
) -> None:
    device.online = online
    device.last_seen = datetime.now(timezone.utc)
    if ip_address:
        device.ip_address = ip_address
    if capabilities is not None:
        await set_device_capabilities(session, device=device, capabilities=capabilities)
    await session.commit()


async def load_device(session: AsyncSession, device_id: UUID) -> Device | None:
    return await session.get(Device, device_id, options=[selectinload(Device.capabilities)])


async def list_devices(session: AsyncSession) -> list[Device]:
    stmt = select(Device).options(selectinload(Device.capabilities)).order_by(Device.name.asc())
    return list((await session.scalars(stmt)).all())
