"""``memory.remember`` / ``memory.recall`` — long-term memory storage.

Persists to the ``memories`` table (created in Phase 1) and is intended as a
minimal building block for the full memory phase (Phase 6).
"""

from __future__ import annotations

from sqlalchemy import select

from core.tools.base import RISK_READ_ONLY, RISK_SAFE, Tool, ToolContext, ToolExecutionError
from database.models import Memory

MEMORY_KINDS = ("fact", "preference", "episodic", "session")


async def _remember(
    content: str,
    kind: str = "fact",
    importance: float = 0.5,
    *,
    context: ToolContext,
) -> dict:
    if context.session is None:
        raise ToolExecutionError("memory.remember requires a database session")
    if kind not in MEMORY_KINDS:
        raise ToolExecutionError(f"invalid memory kind {kind!r}; expected one of {MEMORY_KINDS}")
    memory = Memory(
        user_id=context.user_id,
        kind=kind,
        content=content,
        importance=importance,
        source="agent",
    )
    context.session.add(memory)
    await context.session.commit()
    await context.session.refresh(memory)
    return {"memory_id": str(memory.id), "kind": memory.kind}


async def _recall(
    query: str | None = None,
    limit: int = 5,
    *,
    context: ToolContext,
) -> dict:
    if context.session is None:
        raise ToolExecutionError("memory.recall requires a database session")
    stmt = select(Memory)
    if context.user_id is not None:
        stmt = stmt.where(Memory.user_id == context.user_id)
    if query:
        stmt = stmt.where(Memory.content.ilike(f"%{query}%"))
    stmt = stmt.order_by(Memory.importance.desc()).limit(limit)
    memories = list((await context.session.scalars(stmt)).all())
    return {
        "count": len(memories),
        "memories": [
            {"id": str(m.id), "kind": m.kind, "content": m.content, "importance": m.importance}
            for m in memories
        ],
    }


def build_memory_tools() -> list[Tool]:
    return [
        Tool(
            name="memory.remember",
            description=(
                "Store a fact, preference or memory the user wants JARVIS to remember "
                "for later."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The memory content to store.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(MEMORY_KINDS),
                        "default": "fact",
                    },
                    "importance": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.5,
                    },
                },
                "required": ["content"],
                "additionalProperties": False,
            },
            fn=_remember,
            risk=RISK_SAFE,
            timeout=10.0,
        ),
        Tool(
            name="memory.recall",
            description=(
                "Retrieve stored memories, optionally matching a query. Use before "
                "answering anything that references things the user asked you to remember."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional text to match."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "additionalProperties": False,
            },
            fn=_recall,
            risk=RISK_READ_ONLY,
            timeout=10.0,
        ),
    ]
