"""Tests for Windows companion tool dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.config import settings
from core.devices.manager import DeviceOfflineError
from core.tools.base import ToolContext, ToolExecutionError
from core.tools.builtins.windows_tools import build_windows_tools
from database.base import Base
from database.models import Device, DeviceCapability


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
        self.online_ids: set[UUID] = set()

    def online_device_ids(self) -> set[UUID]:
        return self.online_ids

    async def dispatch(
        self,
        device_id: UUID,
        action: str,
        parameters: dict,
        *,
        tool: str | None = None,
    ) -> dict:
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
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
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
async def test_open_url_normalizes_known_website_name(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
    await session.commit()

    manager = FakeDeviceManager()
    await _tools()["windows.open_url"].run(
        {"device_name": "Achuthan-Laptop", "url": "YouTube"},
        ToolContext(session=session, device_manager=manager),
    )

    assert manager.calls == [
        (device.id, "open_url", {"url": "https://www.youtube.com"})
    ]


@pytest.mark.asyncio
async def test_open_url_normalizes_bare_domain(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
    await session.commit()

    manager = FakeDeviceManager()
    await _tools()["windows.open_url"].run(
        {"device_name": "Achuthan-Laptop", "url": "github.com"},
        ToolContext(session=session, device_manager=manager),
    )

    assert manager.calls == [(device.id, "open_url", {"url": "https://github.com"})]


@pytest.mark.asyncio
async def test_open_url_builds_google_search_url(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
    await session.commit()

    manager = FakeDeviceManager()
    await _tools()["windows.open_url"].run(
        {"device_name": "Achuthan-Laptop", "search_query": "Yamaha engine 34354345"},
        ToolContext(session=session, device_manager=manager),
    )

    assert manager.calls == [
        (
            device.id,
            "open_url",
            {"url": "https://www.google.com/search?q=Yamaha+engine+34354345"},
        )
    ]


@pytest.mark.asyncio
async def test_windows_tool_reports_offline_device(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.system_info"))
    await session.commit()

    manager = FakeDeviceManager()
    manager.offline = True
    with pytest.raises(ToolExecutionError, match="offline"):
        await _tools()["windows.system_info"].run(
            {"device_name": "Achuthan-Laptop"},
            ToolContext(session=session, device_manager=manager),
        )


@pytest.mark.asyncio
async def test_open_url_rejects_unsafe_scheme(session: AsyncSession) -> None:
    device = Device(name="Achuthan-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
    await session.commit()

    with pytest.raises(ToolExecutionError, match="only http and https"):
        await _tools()["windows.open_url"].run(
            {"device_name": "Achuthan-Laptop", "url": "file:///C:/Windows/System32/calc.exe"},
            ToolContext(session=session, device_manager=FakeDeviceManager()),
        )


@pytest.mark.asyncio
async def test_default_windows_device_is_used(session: AsyncSession, monkeypatch) -> None:
    device = Device(name="Default-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.system_info"))
    await session.commit()
    monkeypatch.setattr(settings, "default_windows_device", str(device.id))

    manager = FakeDeviceManager()
    result = await _tools()["windows.system_info"].run(
        {},
        ToolContext(session=session, device_manager=manager),
    )

    assert result["device_name"] == "Default-Laptop"
    assert manager.calls == [(device.id, "system_info", {})]


@pytest.mark.asyncio
async def test_windows_device_alias_is_used(session: AsyncSession, monkeypatch) -> None:
    device = Device(name="Office-PC", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.system_info"))
    await session.commit()
    monkeypatch.setattr(settings, "windows_device_aliases", f"pc={device.id},my laptop={device.id}")

    manager = FakeDeviceManager()
    result = await _tools()["windows.system_info"].run(
        {"device_name": "my laptop"},
        ToolContext(session=session, device_manager=manager),
    )

    assert result["device_name"] == "Office-PC"


@pytest.mark.asyncio
async def test_generic_laptop_name_uses_only_registered_windows_device(
    session: AsyncSession,
) -> None:
    device = Device(name="Only-Laptop", device_type="windows")
    session.add(device)
    await session.flush()
    session.add(DeviceCapability(device_id=device.id, capability="windows.system_info"))
    await session.commit()

    manager = FakeDeviceManager()
    result = await _tools()["windows.system_info"].run(
        {"device_name": "my laptop"},
        ToolContext(session=session, device_manager=manager),
    )

    assert result["device_name"] == "Only-Laptop"


@pytest.mark.asyncio
async def test_only_online_windows_device_is_used(session: AsyncSession) -> None:
    offline = Device(name="Offline-Laptop", device_type="windows")
    online = Device(name="Online-Laptop", device_type="windows")
    session.add_all([offline, online])
    await session.flush()
    session.add(DeviceCapability(device_id=offline.id, capability="windows.system_info"))
    session.add(DeviceCapability(device_id=online.id, capability="windows.system_info"))
    await session.commit()

    manager = FakeDeviceManager()
    manager.online_ids = {online.id}
    result = await _tools()["windows.system_info"].run(
        {},
        ToolContext(session=session, device_manager=manager),
    )

    assert result["device_name"] == "Online-Laptop"


@pytest.mark.asyncio
async def test_multiple_windows_devices_require_specific_device(session: AsyncSession) -> None:
    first = Device(name="Laptop-One", device_type="windows")
    second = Device(name="Laptop-Two", device_type="windows")
    session.add_all([first, second])
    await session.commit()

    with pytest.raises(ToolExecutionError, match="multiple Windows devices"):
        await _tools()["windows.system_info"].run(
            {},
            ToolContext(session=session, device_manager=FakeDeviceManager()),
        )
