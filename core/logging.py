"""Structured logging setup.

Emits JSON-formatted log records so the platform can be observed and audited
as a machine stream. All secrets must be excluded from log output at the
call sites.
"""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from core.config import settings


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp"},
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Keep third-party request/access logs quieter by default.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
