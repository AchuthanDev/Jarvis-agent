"""Shared FastAPI dependencies."""

from fastapi import Request

from core.llm.base import LLMProvider
from database.session import get_db

__all__ = ["get_db", "get_llm"]


def get_llm(request: Request) -> LLMProvider | None:
    """Return the configured LLM provider (``None`` when not configured)."""
    return getattr(request.app.state, "llm", None)
