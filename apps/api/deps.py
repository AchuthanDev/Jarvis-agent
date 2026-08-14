"""Shared FastAPI dependencies."""

from database.session import get_db

__all__ = ["get_db"]
