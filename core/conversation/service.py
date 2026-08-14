"""Conversation persistence and history assembly.

Separates the database access (this module) from the transport/API layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.conversation.system_prompt import build_system_prompt
from core.llm.types import ChatMessage
from database.models import Conversation, Message

DEFAULT_HISTORY_LIMIT = 40


async def resolve_or_create_conversation(
    session: AsyncSession,
    *,
    conversation_id: UUID | None,
    user_id: UUID | None,
    first_message: str,
) -> Conversation:
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    conversation = Conversation(user_id=user_id, title=first_message[:60])
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def add_message(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    role: str,
    content: str,
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def load_history(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> Sequence[Message]:
    """Return the most recent ``limit`` messages, oldest first."""
    rows = list(
        (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    rows.reverse()
    return rows


def build_chat_messages(
    history: Sequence[Message], *, system_prompt: str | None = None
) -> list[ChatMessage]:
    """Assemble the provider payload: system prompt + conversation history."""
    messages = [
        ChatMessage(role="system", content=system_prompt or build_system_prompt())
    ]
    messages.extend(
        ChatMessage(role=message.role, content=message.content)
        for message in history
        if message.role in ("user", "assistant")
    )
    return messages
