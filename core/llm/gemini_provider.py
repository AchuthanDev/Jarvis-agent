"""Google Gemini provider (google-genai SDK, async via ``client.aio``)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from core.llm.base import LLMProvider
from core.llm.errors import LLMError
from core.llm.types import ChatMessage, LLMResponse

_ROLE_MAP = {"assistant": "model"}


class GeminiProvider(LLMProvider):
    def __init__(self, model: str, api_key: str = "") -> None:
        from google import genai

        self.name = "gemini"
        self.model = model
        self._client = genai.Client(api_key=api_key or "not-set")

    @property
    def base_url(self) -> str | None:
        return None

    def _contents(self, messages: Sequence[ChatMessage]) -> list:
        from google.genai import types

        contents: list = []
        for message in messages:
            if message.role == "system":
                continue
            role = _ROLE_MAP.get(message.role, message.role)
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=message.content)],
                )
            )
        return contents

    def _config(self, system: str | None, temperature: float, max_tokens: int | None):
        from google.genai import types

        kwargs: dict = {"temperature": temperature}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if system:
            kwargs["system_instruction"] = system
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _system(messages: Sequence[ChatMessage]) -> str | None:
        return next((m.content for m in messages if m.role == "system"), None)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=self._contents(messages),
                config=self._config(self._system(messages), temperature, max_tokens),
            )
        except Exception as exc:
            raise LLMError(f"Gemini request failed: {type(exc).__name__}") from exc
        return LLMResponse(content=(response.text or "") if response else "")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=self._contents(messages),
                config=self._config(self._system(messages), temperature, max_tokens),
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise LLMError(f"Gemini stream failed: {type(exc).__name__}") from exc

    async def close(self) -> None:
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()
