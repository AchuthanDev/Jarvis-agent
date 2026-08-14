"""Tests for the provider implementations, using mocked HTTP layers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import openai
import pytest

from core.llm.errors import LLMError
from core.llm.gemini_provider import GeminiProvider
from core.llm.ollama_provider import OllamaProvider
from core.llm.openai_provider import OpenAIProvider
from core.llm.types import ChatMessage, LLMResponse


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = SimpleNamespace(content=content)
        self.finish_reason = "stop"


class _FakeUsage:
    def model_dump(self) -> dict:
        return {"prompt_tokens": 3, "completion_tokens": 5}


class _FakeOpenAIResponse:
    def __init__(self, content: str = "hi") -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


async def _fake_deltas() -> AsyncIterator[SimpleNamespace]:
    for piece in ("hel", "lo"):
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])


class _FakeOpenAICompletions:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def create(self, **kwargs):
        if self._fail:
            raise openai.APIError("boom")
        if kwargs.get("stream"):
            return _fake_deltas()
        return _FakeOpenAIResponse()


class _FakeOpenAIChat:
    def __init__(self, completions: _FakeOpenAICompletions) -> None:
        self.completions = completions


class _FakeOpenAIClient:
    def __init__(self, completions: _FakeOpenAICompletions) -> None:
        self.chat = _FakeOpenAIChat(completions)
        self.base_url = "https://api.openai.com/v1"

    async def close(self) -> None:
        return None


def _messages() -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="be concise"),
        ChatMessage(role="user", content="hello"),
    ]


def _make_openai(monkeypatch, *, fail: bool = False) -> OpenAIProvider:
    completions = _FakeOpenAICompletions(fail=fail)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: _FakeOpenAIClient(completions))
    return OpenAIProvider(model="gpt-4o-mini", api_key="test-key")


@pytest.mark.asyncio
async def test_openai_chat(monkeypatch) -> None:
    provider = _make_openai(monkeypatch)
    result = await provider.chat(_messages())
    assert isinstance(result, LLMResponse)
    assert result.content == "hi"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 3, "completion_tokens": 5}
    await provider.close()


@pytest.mark.asyncio
async def test_openai_stream(monkeypatch) -> None:
    provider = _make_openai(monkeypatch)
    deltas = [delta async for delta in provider.stream(_messages())]
    assert deltas == ["hel", "lo"]
    await provider.close()


@pytest.mark.asyncio
async def test_openai_chat_raises_llm_error(monkeypatch) -> None:
    provider = _make_openai(monkeypatch, fail=True)
    with pytest.raises(LLMError):
        await provider.chat(_messages())
    await provider.close()


class _FakeOllamaResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeOllamaStream:
    def __init__(self) -> None:
        self._lines = ['{"message": {"content": "one"}}', '{"message": {"content": "two"}}']

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line


class _FakeOllamaClient:
    async def post(self, url: str, json: dict):
        return _FakeOllamaResponse({"message": {"content": "ok"}, "prompt_eval_count": 2})

    def stream(self, method: str, url: str, json: dict):
        return _FakeOllamaStream()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_ollama_chat(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeOllamaClient())
    provider = OllamaProvider(model="llama3", base_url="http://test:11434")
    result = await provider.chat(_messages())
    assert result.content == "ok"
    assert result.usage == {"prompt_eval_count": 2, "eval_count": None}
    assert provider.base_url == "http://test:11434"
    await provider.close()


@pytest.mark.asyncio
async def test_ollama_stream(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeOllamaClient())
    provider = OllamaProvider(model="llama3", base_url="http://test:11434")
    deltas = [delta async for delta in provider.stream(_messages())]
    assert deltas == ["one", "two"]
    await provider.close()


class _FakeGeminiModels:
    def __init__(self) -> None:
        self.generate_content_called = False

    async def generate_content(self, **kwargs) -> SimpleNamespace:
        self.generate_content_called = True
        return SimpleNamespace(text="gemini says hi")

    async def generate_content_stream(self, **kwargs) -> AsyncIterator[SimpleNamespace]:
        async def _gen() -> AsyncIterator[SimpleNamespace]:
            for piece in ("gemini ", "stream"):
                yield SimpleNamespace(text=piece)

        return _gen()


class _FakeGeminiAio:
    def __init__(self) -> None:
        self.models = _FakeGeminiModels()


class _FakeGeminiClient:
    def __init__(self) -> None:
        self.aio = _FakeGeminiAio()


def _make_gemini(monkeypatch) -> GeminiProvider:
    from google import genai

    monkeypatch.setattr(genai, "Client", lambda **kw: _FakeGeminiClient())
    return GeminiProvider(model="gemini-2.5-flash", api_key="test-key")


@pytest.mark.asyncio
async def test_gemini_chat(monkeypatch) -> None:
    provider = _make_gemini(monkeypatch)
    result = await provider.chat(_messages())
    assert result.content == "gemini says hi"
    assert provider.model == "gemini-2.5-flash"
    await provider.close()


@pytest.mark.asyncio
async def test_gemini_stream(monkeypatch) -> None:
    provider = _make_gemini(monkeypatch)
    deltas = [delta async for delta in provider.stream(_messages())]
    assert deltas == ["gemini ", "stream"]
    await provider.close()
