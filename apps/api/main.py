"""JARVIS API application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.api.routers import chat, devices, health
from core import __version__
from core.config import settings
from core.devices.manager import DeviceConnectionManager
from core.llm.registry import create_provider
from core.logging import setup_logging
from core.security.permissions import PermissionPolicy
from core.tools.builtins import register_default_tools
from core.tools.registry import ToolRegistry
from database.session import dispose_engine, get_sessionmaker

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        setup_logging()
        logger.info(
            "JARVIS API starting",
            extra={"version": __version__, "environment": settings.environment},
        )
        app.state.llm = create_provider(settings)
        app.state.db_sessionmaker = get_sessionmaker()
        app.state.device_connections = DeviceConnectionManager(
            command_timeout=settings.device_command_timeout_seconds,
            heartbeat_timeout=settings.device_presence_timeout_seconds,
        )
        if app.state.llm is not None:
            logger.info(
                "LLM provider ready",
                extra={"provider": app.state.llm.name, "model": app.state.llm.model},
            )
        else:
            logger.warning("No LLM configured — chat endpoints will return 503")

        app.state.tools = None
        app.state.permissions = PermissionPolicy(settings.tool_max_autonomous_risk)
        if settings.tools_enabled:
            registry = ToolRegistry()
            register_default_tools(registry)
            app.state.tools = registry
            logger.info("Tool registry ready", extra={"tools": registry.names()})
        else:
            logger.warning("Tools disabled — chat will run without tool calling")
        yield
        if app.state.llm is not None:
            await app.state.llm.close()
        await app.state.device_connections.close_all()
        await dispose_engine()
        logger.info("JARVIS API stopped")

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description="Personal distributed AI operating layer.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router)
    app.include_router(devices.router)

    static_dir = settings.static_dir
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
