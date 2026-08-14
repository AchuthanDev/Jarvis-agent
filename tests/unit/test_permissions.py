"""Tests for the permission policy gate."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from core.security.permissions import PermissionPolicy
from core.tools.base import RISK_APPROVAL, RISK_READ_ONLY, ToolContext
from database.base import Base
from database.models import Device, Permission, User


@pytest.mark.asyncio
async def test_low_risk_allowed_within_threshold() -> None:
    decision = await PermissionPolicy().decide(None, ToolContext(), "x", RISK_READ_ONLY)
    assert decision.allowed


@pytest.mark.asyncio
async def test_high_risk_denied_beyond_threshold() -> None:
    decision = await PermissionPolicy().decide(None, ToolContext(), "x", RISK_APPROVAL)
    assert not decision.allowed
    assert "threshold" in decision.reason


@pytest.mark.asyncio
async def test_threshold_is_inclusive() -> None:
    decision = await PermissionPolicy(max_autonomous_risk=2).decide(
        None, ToolContext(), "x", RISK_APPROVAL
    )
    assert decision.allowed


@pytest.mark.asyncio
async def test_explicit_allow_overrides_risk() -> None:
    session = _SessionWithPermission(effect="allow")
    decision = await PermissionPolicy().decide(session, ToolContext(), "x", RISK_APPROVAL)
    assert decision.allowed
    assert "explicit permission rule" in decision.reason


@pytest.mark.asyncio
async def test_explicit_deny_wins() -> None:
    session = _SessionWithPermission(effect="deny")
    decision = await PermissionPolicy().decide(session, ToolContext(), "x", RISK_READ_ONLY)
    assert not decision.allowed


class _SessionWithPermission:
    def __init__(self, effect: str) -> None:
        self._effect = effect

    async def scalars(self, stmt) -> object:
        from database.models import Permission

        row = Permission(tool="x", effect=self._effect)
        return _ScalarsResult([row])


class _ScalarsResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_scoped_rule_does_not_apply_to_anonymous_context(
    db_session: AsyncSession,
) -> None:
    user = User(username=f"user-{uuid4()}")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Permission(user_id=user.id, tool="x", effect="allow"))
    await db_session.commit()

    decision = await PermissionPolicy().decide(
        db_session,
        ToolContext(user_id=None),
        "x",
        RISK_APPROVAL,
    )

    assert not decision.allowed
    assert "threshold" in decision.reason


@pytest.mark.asyncio
async def test_device_scoped_rule_applies_only_to_matching_device(
    db_session: AsyncSession,
) -> None:
    device = Device(name="Laptop", device_type="windows")
    db_session.add(device)
    await db_session.flush()
    db_session.add(Permission(device_id=device.id, tool="x", effect="allow"))
    await db_session.commit()

    unmatched = await PermissionPolicy().decide(
        db_session,
        ToolContext(device_id=uuid4()),
        "x",
        RISK_APPROVAL,
    )
    matched = await PermissionPolicy().decide(
        db_session,
        ToolContext(device_id=device.id),
        "x",
        RISK_APPROVAL,
    )

    assert not unmatched.allowed
    assert matched.allowed
