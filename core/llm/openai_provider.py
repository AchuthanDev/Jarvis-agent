"""OpenAI-compatible provider.

Covers OpenAI, Groq, and any vendor exposing an OpenAI-compatible chat
completions API (OpenRouter, LM Studio, Ollama's ``/v1`` endpoint, ...).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from core.llm.base import LLMProvider
from core.llm.errors import LLMError, LLMRateLimitError
from core.llm.types import ChatMessage, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str = "",
        base_url: str | None = None,
        name: str = "openai",
    ) -> None:
        from openai import AsyncOpenAI

        self.name = name
        self.model = model
        self._base_url = base_url
        self._client = AsyncOpenAI(api_key=api_key or "not-set", base_url=base_url)

    @property
    def base_url(self) -> str | None:
        return self._base_url

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        kwargs: dict = {"temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[m.to_dict() for m in messages],
                **kwargs,
            )
        except Exception as exc:
            if type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429:
                headers = getattr(getattr(exc, "response", None), "headers", None) or getattr(exc, "headers", {}) or {}
                retry_after = headers.get("retry-after") or headers.get("Retry-After")
                raise LLMRateLimitError(
                    provider=self.name,
                    retry_after=str(retry_after) if retry_after else None,
                ) from exc
            raise LLMError(f"OpenAI-compatible request failed: {type(exc).__name__}") from exc
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason,
            usage=response.usage.model_dump() if response.usage else {},
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict = {"temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[m.to_dict() for m in messages],
                stream=True,
                **kwargs,
            )
        except Exception as exc:
            if type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429:
                headers = getattr(getattr(exc, "response", None), "headers", None) or getattr(exc, "headers", {}) or {}
                retry_after = headers.get("retry-after") or headers.get("Retry-After")
                raise LLMRateLimitError(
                    provider=self.name,
                    retry_after=str(retry_after) if retry_after else None,
                ) from exc
            raise LLMError(f"OpenAI-compatible request failed: {type(exc).__name__}") from exc

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            raise LLMError(f"OpenAI-compatible stream failed: {type(exc).__name__}") from exc

    async def close(self) -> None:
        await self._client.close()
