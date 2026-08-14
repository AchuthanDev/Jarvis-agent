"""Chat endpoints.

- ``POST /api/chat``                — non-streaming reply.
- ``POST /api/chat/stream``         — server-sent-events reply.
- ``GET  /api/conversations``       — list conversations.
- ``POST /api/conversations``       — create an empty conversation.
- ``GET  /api/conversations/{id}/messages`` — message history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db, get_llm
from core.config import settings
from core.conversation.service import (
    add_message,
    build_chat_messages,
    load_history,
    resolve_or_create_conversation,
)
from core.llm.base import LLMProvider
from core.llm.errors import LLMError
from database.models import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str


class ConversationSummary(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _require_llm(llm: LLMProvider | None) -> LLMProvider:
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="The language model is not configured. Set LLM_PROVIDER and LLM_MODEL in the environment.",
        )
    return llm


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_db),
    llm: LLMProvider | None = Depends(get_llm),
) -> ChatResponse:
    provider = await _require_llm(llm)
    conversation = await resolve_or_create_conversation(
        session,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        first_message=request.message,
    )
    await add_message(
        session, conversation_id=conversation.id, role="user", content=request.message
    )
    history = await load_history(session, conversation_id=conversation.id)
    messages = build_chat_messages(history)

    try:
        response = await provider.chat(
            messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    except LLMError as exc:
        logger.warning(
            "chat failed",
            extra={
                "conversation_id": str(conversation.id),
                "provider": provider.name,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=502, detail="I couldn't reach the language model right now."
        ) from exc

    await add_message(
        session, conversation_id=conversation.id, role="assistant", content=response.content
    )
    logger.info(
        "chat completed",
        extra={
            "conversation_id": str(conversation.id),
            "provider": provider.name,
            "tokens": len(response.content),
        },
    )
    return ChatResponse(conversation_id=conversation.id, reply=response.content)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    session: AsyncSession = Depends(get_db),
    llm: LLMProvider | None = Depends(get_llm),
) -> StreamingResponse:
    provider = await _require_llm(llm)
    conversation = await resolve_or_create_conversation(
        session,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        first_message=request.message,
    )
    await add_message(
        session, conversation_id=conversation.id, role="user", content=request.message
    )
    history = await load_history(session, conversation_id=conversation.id)
    messages = build_chat_messages(history)
    conversation_id = conversation.id

    async def event_generator():
        full: list[str] = []
        yield _sse("start", {"conversation_id": str(conversation_id)})
        try:
            async for delta in provider.stream(
                messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                full.append(delta)
                yield _sse("delta", {"delta": delta})
        except LLMError as exc:
            logger.warning(
                "chat stream failed",
                extra={
                    "conversation_id": str(conversation_id),
                    "provider": provider.name,
                    "error": str(exc),
                },
            )
            yield _sse("error", {"message": "I couldn't reach the language model right now."})
            return

        content = "".join(full)
        await add_message(
            session, conversation_id=conversation_id, role="assistant", content=content
        )
        yield _sse("done", {"conversation_id": str(conversation_id), "content": content})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    conversations = list(
        (
            await session.scalars(
                select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            )
        ).all()
    )
    return [
        ConversationSummary(
            id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at
        )
        for c in conversations
    ]


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
async def create_conversation(
    user_id: UUID | None = None,
    session: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    conversation = Conversation(user_id=user_id, title=None)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return list(
        (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        ).all()
    )
