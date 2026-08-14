"""Shared fixtures for API tests.

Uses an in-memory SQLite database (aiosqlite) with a single shared
connection, so tests are self-contained and never touch the real Postgres.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from apps.api.deps import get_db, get_llm
from apps.api.main import create_app
from core.llm.base import LLMProvider
from core.llm.types import ChatMessage, LLMResponse
from database.base import Base


@pytest.fixture(scope="session")
def engine() -> AsyncEngine:
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async def _create_tables() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    yield test_engine
    asyncio.run(test_engine.dispose())


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class FakeProvider(LLMProvider):
    """Deterministic stand-in for the real LLM provider."""

    name = "fake"
    model = "fake-model"
    reply = "Fake reply."

    def __init__(self) -> None:
        self.last_messages: list[ChatMessage] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.last_messages = list(messages)
        return LLMResponse(content=self.reply)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self.last_messages = list(messages)
        for part in ("Fake ", "reply."):
            yield part


@pytest.fixture
def fake_llm() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(sessionmaker: async_sessionmaker[AsyncSession], fake_llm: FakeProvider) -> TestClient:
    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client
