"""Provider factory — maps configuration to a concrete LLM provider.

Configuration-driven: changing ``LLM_PROVIDER`` / ``LLM_MODEL`` /
``LLM_BASE_URL`` in the environment is enough to switch vendors.
"""

from __future__ import annotations

import logging

from core.config import Settings
from core.llm.base import LLMProvider
from core.llm.errors import LLMConfigurationError
from core.llm.gemini_provider import GeminiProvider
from core.llm.ollama_provider import DEFAULT_BASE_URL, OllamaProvider
from core.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# provider -> (provider class, default OpenAI-compatible base URL)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def create_provider(settings: Settings) -> LLMProvider | None:
    """Create a provider from settings, or ``None`` when no model is configured."""
    provider = settings.llm_provider.strip().lower()
    model = settings.llm_model.strip()

    if not model:
        logger.info("LLM provider not configured (LLM_MODEL is empty)")
        return None

    if provider in ("openai", "openai_compatible"):
        base_url = settings.llm_base_url.strip() or None
        return OpenAIProvider(
            model=model,
            api_key=settings.llm_api_key,
            base_url=base_url,
            name="openai" if provider == "openai" else "openai_compatible",
        )

    if provider == "groq":
        return OpenAIProvider(
            model=model,
            api_key=settings.llm_api_key,
            base_url=GROQ_BASE_URL,
            name="groq",
        )

    if provider == "gemini":
        return GeminiProvider(model=model, api_key=settings.llm_api_key)

    if provider == "ollama":
        base_url = settings.llm_base_url.strip() or DEFAULT_BASE_URL
        return OllamaProvider(model=model, base_url=base_url)

    raise LLMConfigurationError(f"unsupported LLM_PROVIDER: {settings.llm_provider!r}")
