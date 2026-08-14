"""Shared FastAPI dependencies."""

from fastapi import Request

from core.llm.base import LLMProvider
from core.security.permissions import PermissionPolicy
from core.tools.registry import ToolRegistry
from database.session import get_db

__all__ = ["get_db", "get_llm", "get_permission_policy", "get_tools"]


def get_llm(request: Request) -> LLMProvider | None:
    """Return the configured LLM provider (``None`` when not configured)."""
    return getattr(request.app.state, "llm", None)


def get_tools(request: Request) -> ToolRegistry | None:
    """Return the tool registry (``None`` when tool calling is disabled)."""
    return getattr(request.app.state, "tools", None)


def get_permission_policy(request: Request) -> PermissionPolicy:
    return getattr(request.app.state, "permissions", PermissionPolicy())
