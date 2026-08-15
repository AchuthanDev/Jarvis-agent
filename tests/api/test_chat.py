"""Tests for the chat and conversation endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from core.llm.base import LLMProvider
from core.llm.types import ChatMessage, LLMResponse
from database.models import Device, DeviceCapability, ToolCall
from tests.api.conftest import FakeProvider


def test_chat_creates_conversation_and_replies(client: TestClient, fake_llm: FakeProvider) -> None:
    response = client.post("/api/chat", json={"message": "Hello JARVIS"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Fake reply."
    assert body["conversation_id"]
    assert fake_llm.last_messages[0].role == "system"
    assert fake_llm.last_messages[-1].content == "Hello JARVIS"


def test_chat_appends_to_existing_conversation(
    client: TestClient, fake_llm: FakeProvider
) -> None:
    first = client.post("/api/chat", json={"message": "First"}).json()
    second = client.post(
        "/api/chat", json={"conversation_id": first["conversation_id"], "message": "Second"}
    )

    assert second.status_code == 200
    roles = [m.role for m in fake_llm.last_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert fake_llm.last_messages[1].content == "First"
    assert fake_llm.last_messages[2].content == "Fake reply."


def test_chat_with_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.post("/api/chat", json={"conversation_id": str(uuid4()), "message": "hi"})
    assert response.status_code == 404


def test_chat_stream_emits_sse(client: TestClient, fake_llm: FakeProvider) -> None:
    response = client.post("/api/chat/stream", json={"message": "Tell me a story"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: start" in text
    assert "event: delta" in text
    assert "event: done" in text
    assert "Fake " in text


def test_list_and_create_conversations(client: TestClient) -> None:
    created = client.post("/api/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    ids = [conversation["id"] for conversation in listing.json()]
    assert conversation_id in ids


def test_get_messages_for_conversation(client: TestClient) -> None:
    chat_response = client.post("/api/chat", json={"message": "Persist me"}).json()

    messages = client.get(
        f"/api/conversations/{chat_response['conversation_id']}/messages"
    )
    assert messages.status_code == 200
    body = messages.json()
    assert [message["role"] for message in body] == ["user", "assistant"]
    assert body[0]["content"] == "Persist me"


def test_get_messages_for_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/conversations/{uuid4()}/messages")
    assert response.status_code == 404


def test_chat_returns_503_when_llm_not_configured(
    sessionmaker, engine
) -> None:
    from apps.api.deps import get_db, get_llm
    from apps.api.main import create_app

    app = create_app()

    async def override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: None
    with TestClient(app) as test_client:
        response = test_client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 503


class _ToolProvider(LLMProvider):
    """Provider that requests ``current_time`` once, then answers in prose."""

    name = "tool-fake"
    model = "tool-fake-model"

    def __init__(self) -> None:
        self.replies = ['{"tool": "current_time", "arguments": {}}', "It's now."]

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=self.replies.pop(0))

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield "It's now."


def test_chat_runs_tool_and_records_tool_call(sessionmaker) -> None:
    from apps.api.deps import get_db, get_llm
    from apps.api.main import create_app

    app = create_app()

    async def override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: _ToolProvider()
    with TestClient(app) as test_client:
        response = test_client.post("/api/chat", json={"message": "What time is it?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "It's now."

    async def fetch_rows() -> list[ToolCall]:
        async with sessionmaker() as session:
            return list((await session.scalars(select(ToolCall))).all())

    rows = asyncio.run(fetch_rows())
    assert len(rows) == 1
    assert rows[0].tool == "current_time"
    assert rows[0].status == "executed"
    assert rows[0].parameters == {}


class _WindowsToolProvider(LLMProvider):
    """Provider that requests a Windows URL open once, then confirms completion."""

    name = "windows-tool-fake"
    model = "windows-tool-fake-model"

    def __init__(self) -> None:
        self.replies = [
            '{"tool": "windows.open_url", "arguments": {"url": "https://www.google.com"}}',
            "Google is open on your laptop.",
        ]

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=self.replies.pop(0))

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield "Google is open on your laptop."


class _FakeDeviceManager:
    def __init__(self) -> None:
        self.calls = []

    async def dispatch(self, device_id, action, parameters, *, tool=None, timeout=None):
        self.calls.append((device_id, action, parameters, tool, timeout))
        return {"opened": True, "url": parameters["url"]}

    def online_device_ids(self):
        return set()


def test_chat_routes_open_google_to_windows_tool(sessionmaker) -> None:
    from apps.api.deps import get_db, get_device_connections, get_llm
    from apps.api.main import create_app

    async def create_device() -> None:
        async with sessionmaker() as session:
            device = Device(name="My-Laptop", device_type="windows")
            session.add(device)
            await session.flush()
            session.add(DeviceCapability(device_id=device.id, capability="windows.open_url"))
            await session.commit()

    asyncio.run(create_device())

    app = create_app()
    manager = _FakeDeviceManager()

    async def override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: _WindowsToolProvider()
    app.dependency_overrides[get_device_connections] = lambda: manager
    with TestClient(app) as test_client:
        response = test_client.post("/api/chat", json={"message": "Open Google on my laptop."})

    assert response.status_code == 200
    assert response.json()["reply"] == "Google is open on your laptop."
    assert manager.calls[0][1:] == (
        "open_url",
        {"url": "https://www.google.com"},
        "windows.open_url",
        None,
    )
