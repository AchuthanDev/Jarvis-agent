"""Regression tests for provider failures reaching the voice client."""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from device_agents.windows.voice.client import (
    JarvisChatClient,
    JarvisServerError,
    VoiceInteraction,
)
from device_agents.windows.voice.config import VoiceConfig
from device_agents.windows.voice.providers import AudioData
from device_agents.windows.voice.state import VoiceState
from device_agents.windows.voice.stt import NullSTT
from device_agents.windows.voice.tts import NullTTS


def _config() -> VoiceConfig:
    return VoiceConfig(
        server_url="http://jarvis.local:8000",
        device_id="device-id",
        device_token="device-token",
        device_name="Laptop",
        voice_enabled=True,
        wakeword_enabled=False,
        wakeword_phrase="hey jarvis",
        stt_provider="null",
        stt_model="base",
        tts_provider="null",
        tts_voice="",
        audio_input_device="",
        audio_output_device="",
        vad_enabled=True,
        vad_threshold=0.01,
        silence_seconds=1.0,
        no_speech_timeout_seconds=8.0,
        max_record_seconds=30.0,
        sample_rate=16000,
    )


def _http_error(code: int, body: dict, headers: dict[str, str] | None = None):
    from urllib.error import HTTPError

    return HTTPError(
        "http://jarvis.local:8000/api/chat",
        code,
        "error",
        headers or {},
        io.BytesIO(json.dumps(body).encode()),
    )


def test_voice_client_maps_structured_provider_rate_limit(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise _http_error(
            429,
            {
                "detail": {
                    "error": {
                        "code": "provider_rate_limited",
                        "provider": "groq",
                        "retryable": True,
                        "message": "The AI provider is temporarily rate limited.",
                    }
                }
            },
            {"Retry-After": "30"},
        )

    monkeypatch.setattr("device_agents.windows.voice.client.request.urlopen", fail)

    with pytest.raises(JarvisServerError) as raised:
        asyncio.run(JarvisChatClient(_config()).send_transcript("What time is it?"))

    assert raised.value.code == "provider_rate_limited"
    assert raised.value.retryable is True
    assert raised.value.retry_after == "30"


def test_voice_client_maps_server_5xx_without_exposing_detail(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise _http_error(502, {"detail": "internal provider traceback"})

    monkeypatch.setattr("device_agents.windows.voice.client.request.urlopen", fail)

    with pytest.raises(JarvisServerError) as raised:
        asyncio.run(JarvisChatClient(_config()).send_transcript("Hello"))

    assert raised.value.code == "server_error"
    assert raised.value.status_code == 502
    assert "traceback" not in str(raised.value)


@pytest.mark.asyncio
async def test_voice_returns_to_standby_after_provider_rate_limit(capsys) -> None:
    class Recorder:
        async def record_until_silence(self) -> AudioData:
            return AudioData(samples=[1], sample_rate=16000)

        async def stop(self) -> None:
            pass

    class Playback:
        async def play(self, audio: bytes) -> None:
            del audio

        async def stop(self) -> None:
            pass

        async def close(self) -> None:
            pass

    class Chat:
        config = _config()

        async def send_transcript(self, transcript: str, *, conversation_id=None):
            del transcript, conversation_id
            raise JarvisServerError(
                "The AI provider is temporarily rate limited.",
                code="provider_rate_limited",
                status_code=429,
                retryable=True,
            )

    interaction = VoiceInteraction(
        recorder=Recorder(),
        stt=NullSTT("Open Google."),
        tts=NullTTS(),
        playback=Playback(),
        chat=Chat(),
    )

    assert await interaction.push_to_talk_once() is None
    assert interaction.state.state == VoiceState.IDLE
    assert "temporarily rate-limited" in capsys.readouterr().out
