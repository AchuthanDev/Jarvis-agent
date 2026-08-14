"""JARVIS API application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import health
from core import __version__
from core.config import settings
from core.logging import setup_logging
from database.session import dispose_engine

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        setup_logging()
        logger.info(
            "JARVIS API starting",
            extra={"version": __version__, "environment": settings.environment},
        )
        yield
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
