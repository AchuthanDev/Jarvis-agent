"""Tests for memory tools (DB-backed) using an in-memory SQLite session."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from core.tools.base import ToolContext, ToolExecutionError
from core.tools.builtins.memory_tools import build_memory_tools
from core.tools.validation import ToolValidationError
from database.base import Base


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _tools() -> dict[str, object]:
    return {tool.name: tool for tool in build_memory_tools()}


@pytest.mark.asyncio
async def test_remember_and_recall(sessionmaker) -> None:
    tools = _tools()
    async with sessionmaker() as session:
        context = ToolContext(session=session)
        remembered = await tools["memory.remember"].run(
            {"content": "The user prefers coffee over tea", "kind": "preference"}, context
        )
        assert remembered["kind"] == "preference"
        assert remembered["memory_id"]

        recalled = await tools["memory.recall"].run({"query": "coffee"}, context)
        assert recalled["count"] == 1
        assert "coffee over tea" in recalled["memories"][0]["content"]

        empty = await tools["memory.recall"].run({"query": "noodles"}, context)
        assert empty["count"] == 0


@pytest.mark.asyncio
async def test_remember_rejects_invalid_kind(sessionmaker) -> None:
    tools = _tools()
    async with sessionmaker() as session:
        with pytest.raises(ToolValidationError):
            await tools["memory.remember"].run(
                {"content": "x", "kind": "bogus"}, ToolContext(session=session)
            )


@pytest.mark.asyncio
async def test_recall_without_session_raises(sessionmaker) -> None:
    tools = _tools()
    with pytest.raises(ToolExecutionError):
        await tools["memory.recall"].run({"query": "x"}, ToolContext(session=None))
