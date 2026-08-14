"""Tests for the provider factory (core.llm.registry)."""

from __future__ import annotations

import pytest

from core.config import Settings
from core.llm.errors import LLMConfigurationError
from core.llm.gemini_provider import GeminiProvider
from core.llm.ollama_provider import DEFAULT_BASE_URL, OllamaProvider
from core.llm.openai_provider import OpenAIProvider
from core.llm.registry import GROQ_BASE_URL, create_provider


def _settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
    }
    base.update(overrides)
    return Settings(**base)


def test_no_provider_when_model_unset() -> None:
    assert create_provider(_settings(llm_model="")) is None


def test_openai_provider() -> None:
    provider = create_provider(_settings())
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
    assert provider.model == "gpt-4o-mini"
    assert provider.base_url is None


def test_openai_compatible_custom_base_url() -> None:
    provider = create_provider(
        _settings(llm_provider="openai_compatible", llm_base_url="http://localhost:1234/v1")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai_compatible"
    assert provider.base_url == "http://localhost:1234/v1"


def test_groq_provider_uses_groq_base_url() -> None:
    provider = create_provider(_settings(llm_provider="groq", llm_model="llama-3.3-70b-versatile"))
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == GROQ_BASE_URL


def test_gemini_provider() -> None:
    provider = create_provider(_settings(llm_provider="gemini", llm_model="gemini-2.5-flash"))
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_ollama_provider_uses_default_base_url() -> None:
    provider = create_provider(_settings(llm_provider="ollama", llm_model="llama3.1"))
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == DEFAULT_BASE_URL


def test_ollama_provider_respects_custom_base_url() -> None:
    provider = create_provider(
        _settings(llm_provider="ollama", llm_model="llama3.1", llm_base_url="http://host:11434")
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://host:11434"


def test_unknown_provider_raises() -> None:
    with pytest.raises(LLMConfigurationError):
        create_provider(_settings(llm_provider="hologram"))
