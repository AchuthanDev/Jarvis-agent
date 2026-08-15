"""Tests for Windows companion tool dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.devices.manager import DeviceOfflineError
from core.tools.base import ToolContext, ToolExecutionError
from core.tools.builtins.windows_tools import build_windows_tools
from database.base import Base
from database.models import Device


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        yield db
    await engine.dispose()


class FakeDeviceManager:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str, dict]] = []
        self.offline = False

    def online_device_ids(self) -> set[UUID]:
        return {call[0] for call in self.calls}

    async def dispatch(self, device_id: UUID, action: str, parameters: dict) -> dict:
        if self.offline:
            raise DeviceOfflineError("offline")
        self.calls.append((device_id, action, parameters))
        return {"ok": True}


def _tools() -> dict[str, object]:
    return {tool.name: tool for tool in build_windows_tools()}


@pytest.mark.asyncio
async def test_open_url_dispatches_to_named_windows_device(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.commit()

    manager = FakeDeviceManager()
    context = ToolContext(session=session, device_manager=manager)
    result = await _tools()["windows.open_url"].run(
        {"device_name": "Achuthan-Laptop", "url": "https://google.com"},
        context,
    )

    assert result["device_name"] == "Achuthan-Laptop"
    assert manager.calls == [(device.id, "open_url", {"url": "https://google.com"})]


@pytest.mark.asyncio
async def test_windows_tool_reports_offline_device(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.commit()

    manager = FakeDeviceManager()
    manager.offline = True
    with pytest.raises(ToolExecutionError, match="offline"):
        await _tools()["windows.system_info"].run(
            {"device_name": "Achuthan-Laptop"},
            ToolContext(session=session, device_manager=manager),
        )
