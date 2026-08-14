"""Ollama provider (native HTTP API — no SDK dependency)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from core.llm.base import LLMProvider
from core.llm.errors import LLMError
from core.llm.types import ChatMessage, LLMResponse

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self.name = "ollama"
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    @property
    def base_url(self) -> str:
        return self._base_url

    def _payload(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict:
        options: dict = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        return {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
            "options": options,
        }

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json=self._payload(
                    messages, temperature=temperature, max_tokens=max_tokens, stream=False
                ),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {type(exc).__name__}") from exc
        data = response.json()
        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            usage={
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            },
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=self._payload(
                    messages, temperature=temperature, max_tokens=max_tokens, stream=True
                ),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama stream failed: {type(exc).__name__}") from exc

    async def close(self) -> None:
        await self._client.aclose()
