"""The LLM provider interface.

The application depends only on this interface. Providers are swapped via
configuration (see ``core.llm.registry``), so changing models or vendors never
requires touching application code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from core.llm.types import ChatMessage, LLMResponse


class LLMProvider(ABC):
    """Minimal contract implemented by every model provider."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Return a complete response for ``messages``."""

    @abstractmethod
    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield response text deltas for ``messages``."""

    async def close(self) -> None:  # noqa: B027 — optional hook, no-op by default
        """Release any held connections (no-op by default)."""
