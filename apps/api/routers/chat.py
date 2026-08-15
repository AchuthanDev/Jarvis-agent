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

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_db,
    get_device_connections,
    get_llm,
    get_permission_policy,
    get_tools,
)
from core.agent import AgentResult, build_agent_prompt, run_agent_turn
from core.config import settings
from core.conversation.service import (
    add_message,
    build_chat_messages,
    load_history,
    resolve_or_create_conversation,
)
from core.devices.auth import verify_device_token
from core.devices.manager import DeviceConnectionManager
from core.devices.service import load_device
from core.llm.base import LLMProvider
from core.llm.errors import LLMError, LLMRateLimitError
from core.llm.types import ChatMessage
from core.security.permissions import PermissionPolicy
from core.tools.base import ToolContext
from core.tools.registry import ToolRegistry
from database.models import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    source: str = Field(default="text", pattern="^(text|voice)$")
    source_device_id: UUID | None = None
    response_mode: str = Field(default="text", pattern="^(text|voice)$")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str
    message: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


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


async def _run_turn(
    provider: LLMProvider,
    registry: ToolRegistry | None,
    policy: PermissionPolicy,
    device_manager: DeviceConnectionManager,
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID | None,
    messages: list[ChatMessage],
) -> AgentResult:
    """Run one assistant turn, executing tools when enabled."""
    if registry is None or not registry.names():
        response = await provider.chat(
            messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        return AgentResult(reply=response.content, tool_calls=[])
    context = ToolContext(
        session=session,
        conversation_id=conversation_id,
        user_id=user_id,
        device_manager=device_manager,
    )
    result = await run_agent_turn(
        provider,
        registry,
        policy,
        messages,
        context=context,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens or 1024,
    )
    return result


def _tool_call_out(result) -> dict[str, Any]:
    return {
        "tool": result.name,
        "arguments": result.arguments,
        "status": result.status,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


async def _validate_voice_source(
    request: ChatRequest,
    session: AsyncSession,
    token: str | None,
) -> None:
    if request.source != "voice":
        return
    if request.source_device_id is None:
        raise HTTPException(status_code=422, detail="source_device_id is required for voice")
    if not token:
        raise HTTPException(status_code=401, detail="Voice device token is required")
    device = await load_device(session, request.source_device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Voice source device not found")
    if not verify_device_token(token, device.token_hash, settings.jarvis_secret_key):
        raise HTTPException(status_code=401, detail="Invalid voice device token")


def _stream_reply(reply: str):
    """Yield ``reply`` in small chunks as SSE delta events."""
    chunk_size = 64
    for index in range(0, len(reply), chunk_size):
        yield _sse("delta", {"delta": reply[index : index + chunk_size]})


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_jarvis_device_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    llm: LLMProvider | None = Depends(get_llm),
    registry: ToolRegistry | None = Depends(get_tools),
    policy: PermissionPolicy = Depends(get_permission_policy),
    device_manager: DeviceConnectionManager = Depends(get_device_connections),
) -> ChatResponse:
    provider = await _require_llm(llm)
    await _validate_voice_source(request, session, x_jarvis_device_token)
    conversation = await resolve_or_create_conversation(
        session,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        device_id=request.source_device_id,
        first_message=request.message,
    )
    await add_message(
        session, conversation_id=conversation.id, role="user", content=request.message
    )
    history = await load_history(session, conversation_id=conversation.id)
    messages = build_chat_messages(
        history,
        system_prompt=build_agent_prompt(registry, response_mode=request.response_mode),
    )

    try:
        result = await _run_turn(
            provider,
            registry,
            policy,
            device_manager,
            session,
            conversation_id=conversation.id,
            user_id=request.user_id,
            messages=messages,
        )
    except LLMRateLimitError as exc:
        logger.warning(
            "chat rate limited",
            extra={"conversation_id": str(conversation.id), "provider": provider.name},
        )
        error = {
            "code": "provider_rate_limited",
            "provider": exc.provider,
            "retryable": True,
            "message": "The AI provider is temporarily rate limited.",
        }
        headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
        raise HTTPException(status_code=429, detail={"error": error}, headers=headers) from exc
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
        session, conversation_id=conversation.id, role="assistant", content=result.reply
    )
    logger.info(
        "chat completed",
        extra={
            "conversation_id": str(conversation.id),
            "provider": provider.name,
            "tokens": len(result.reply),
        },
    )
    return ChatResponse(
        conversation_id=conversation.id,
        reply=result.reply,
        message=result.reply,
        tool_calls=[_tool_call_out(call) for call in result.tool_calls],
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    x_jarvis_device_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    llm: LLMProvider | None = Depends(get_llm),
    registry: ToolRegistry | None = Depends(get_tools),
    policy: PermissionPolicy = Depends(get_permission_policy),
    device_manager: DeviceConnectionManager = Depends(get_device_connections),
) -> StreamingResponse:
    provider = await _require_llm(llm)
    await _validate_voice_source(request, session, x_jarvis_device_token)
    conversation = await resolve_or_create_conversation(
        session,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        device_id=request.source_device_id,
        first_message=request.message,
    )
    await add_message(
        session, conversation_id=conversation.id, role="user", content=request.message
    )
    history = await load_history(session, conversation_id=conversation.id)
    messages = build_chat_messages(
        history,
        system_prompt=build_agent_prompt(registry, response_mode=request.response_mode),
    )
    conversation_id = conversation.id

    async def event_generator():
        yield _sse("start", {"conversation_id": str(conversation_id)})
        try:
            result = await _run_turn(
                provider,
                registry,
                policy,
                device_manager,
                session,
                conversation_id=conversation_id,
                user_id=request.user_id,
                messages=messages,
            )
            content = result.reply
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

        for event in _stream_reply(content):
            yield event
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
