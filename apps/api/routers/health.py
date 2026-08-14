"""Health endpoints.

- ``GET /api/health/live``  — process is alive (no dependency checks).
- ``GET /api/health/ready`` — process can serve traffic (DB + Redis checked).

Each dependency reports ``ok`` independently; the overall status is
``ready`` only when every critical dependency passes.
"""

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from core import __version__
from core.config import settings
from database.session import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
    }


async def _check_database() -> dict[str, Any]:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        logger.warning("database health check failed: %s", exc)
        return {"ok": False, "error": type(exc).__name__}


async def _check_redis() -> dict[str, Any]:
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    try:
        await client.ping()
        return {"ok": True}
    except Exception as exc:
        logger.warning("redis health check failed: %s", exc)
        return {"ok": False, "error": type(exc).__name__}
    finally:
        await client.aclose()


@router.get("/ready")
async def ready() -> JSONResponse:
    checks = {
        "database": await _check_database(),
        "redis": await _check_redis(),
    }
    ready = all(check["ok"] for check in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "degraded", "checks": checks},
    )
