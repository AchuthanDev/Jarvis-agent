from typing import Any

from fastapi.testclient import TestClient

from apps.api import routers
from apps.api.main import create_app


def test_live_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "JARVIS"
    assert body["version"]


def _patch_checks(monkeypatch, *, ok: bool) -> None:
    async def check_ok() -> dict[str, Any]:
        return {"ok": True}

    async def check_fail() -> dict[str, Any]:
        return {"ok": False, "error": "boom"}

    check = check_ok if ok else check_fail
    monkeypatch.setattr(routers.health, "_check_database", check)
    monkeypatch.setattr(routers.health, "_check_redis", check)


def test_ready_ok_when_all_components_healthy(monkeypatch) -> None:
    _patch_checks(monkeypatch, ok=True)
    with TestClient(create_app()) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert all(check["ok"] for check in body["checks"].values())


def test_ready_degraded_when_any_component_down(monkeypatch) -> None:
    _patch_checks(monkeypatch, ok=False)
    with TestClient(create_app()) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert set(body["checks"].keys()) == {"database", "redis"}
    for check in body["checks"].values():
        assert check["ok"] is False
