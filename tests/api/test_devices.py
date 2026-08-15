"""Tests for device registration, listing, and command dispatch."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db, get_llm
from apps.api.main import create_app
from core.config import settings
from tests.api.conftest import FakeProvider


def _client(sessionmaker, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "device_registration_secret", "register-secret")
    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: FakeProvider()
    client = TestClient(app)
    return client


def _register_windows(client: TestClient) -> dict:
    response = client.post(
        "/api/devices/register",
        json={
            "registration_secret": "register-secret",
            "name": "Achuthan-Laptop",
            "device_type": "windows",
            "operating_system": "Windows",
            "agent_version": "0.1.0",
            "capabilities": ["windows.open_url", "windows.system_info"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_register_and_list_device(sessionmaker, monkeypatch) -> None:
    with _client(sessionmaker, monkeypatch) as client:
        client.app.state.db_sessionmaker = sessionmaker
        registered = _register_windows(client)

        listing = client.get("/api/devices")

    assert listing.status_code == 200
    body = listing.json()
    device = next(item for item in body if item["id"] == registered["device_id"])
    assert device["name"] == "Achuthan-Laptop"
    assert device["online"] is False
    assert "windows.open_url" in device["capabilities"]


def test_register_rejects_bad_secret(sessionmaker, monkeypatch) -> None:
    with _client(sessionmaker, monkeypatch) as client:
        response = client.post(
            "/api/devices/register",
            json={"registration_secret": "wrong", "name": "Laptop"},
        )

    assert response.status_code == 403


def test_command_returns_409_when_device_offline(sessionmaker, monkeypatch) -> None:
    with _client(sessionmaker, monkeypatch) as client:
        client.app.state.db_sessionmaker = sessionmaker
        registered = _register_windows(client)
        response = client.post(
            f"/api/devices/{registered['device_id']}/commands",
            json={"action": "system_info"},
        )

    assert response.status_code == 409
