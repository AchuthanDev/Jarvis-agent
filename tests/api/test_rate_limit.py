"""API mapping for provider rate limits."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_llm
from apps.api.main import create_app
from core.llm.base import LLMProvider
from core.llm.errors import LLMRateLimitError
from core.llm.types import ChatMessage, LLMResponse


class RateLimitedProvider(LLMProvider):
    name = "groq"
    model = "test-model"

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        del messages, temperature, max_tokens
        raise LLMRateLimitError(provider="groq", retry_after="30")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        del messages, temperature, max_tokens
        if False:
            yield ""


def test_api_preserves_structured_provider_rate_limit(sessionmaker) -> None:
    app = create_app()

    async def override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: RateLimitedProvider()
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "What time is it?"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json() == {
        "detail": {
            "error": {
                "code": "provider_rate_limited",
                "provider": "groq",
                "retryable": True,
                "message": "The AI provider is temporarily rate limited.",
            }
        }
    }
