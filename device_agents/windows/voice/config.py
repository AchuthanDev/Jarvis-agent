"""Configuration for the Windows voice client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from device_agents.windows.agent import DEFAULT_CONFIG_FILE, _load_env_file


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    server_url: str
    device_id: str
    device_token: str
    device_name: str
    voice_enabled: bool
    wakeword_enabled: bool
    wakeword_phrase: str
    stt_provider: str
    stt_model: str
    tts_provider: str
    tts_voice: str
    audio_input_device: str
    audio_output_device: str
    vad_enabled: bool
    vad_threshold: float
    silence_seconds: float
    no_speech_timeout_seconds: float
    max_record_seconds: float
    sample_rate: int
    response_mode: str = "voice"

    @classmethod
    def load(cls, config_file: str | Path | None = None) -> VoiceConfig:
        path = Path(config_file or os.environ.get("JARVIS_CONFIG_FILE") or DEFAULT_CONFIG_FILE)
        _load_env_file(path.expanduser().resolve())
        return cls(
            server_url=os.environ.get("JARVIS_SERVER_URL", "http://localhost:8000").rstrip("/"),
            device_id=os.environ.get("JARVIS_DEVICE_ID", ""),
            device_token=os.environ.get("JARVIS_DEVICE_TOKEN", ""),
            device_name=os.environ.get("JARVIS_DEVICE_NAME", "Windows Voice Client"),
            voice_enabled=_bool_env("JARVIS_VOICE_ENABLED", True),
            wakeword_enabled=_bool_env("JARVIS_WAKEWORD_ENABLED", False),
            wakeword_phrase=os.environ.get("JARVIS_WAKEWORD_PHRASE", "hey jarvis"),
            stt_provider=os.environ.get("JARVIS_STT_PROVIDER", "faster_whisper"),
            stt_model=os.environ.get("JARVIS_STT_MODEL", "base"),
            tts_provider=os.environ.get("JARVIS_TTS_PROVIDER", "edge_tts"),
            tts_voice=os.environ.get("JARVIS_TTS_VOICE", "en-US-GuyNeural"),
            audio_input_device=os.environ.get("JARVIS_AUDIO_INPUT_DEVICE", ""),
            audio_output_device=os.environ.get("JARVIS_AUDIO_OUTPUT_DEVICE", ""),
            vad_enabled=_bool_env("JARVIS_VAD_ENABLED", True),
            vad_threshold=_float_env("JARVIS_VAD_THRESHOLD", 0.012),
            silence_seconds=_float_env("JARVIS_VAD_SILENCE_SECONDS", 1.0),
            no_speech_timeout_seconds=_float_env("JARVIS_NO_SPEECH_TIMEOUT_SECONDS", 8.0),
            max_record_seconds=_float_env("JARVIS_MAX_RECORD_SECONDS", 30.0),
            sample_rate=_int_env("JARVIS_AUDIO_SAMPLE_RATE", 16000),
        )

    def validate_for_chat(self) -> None:
        if not self.server_url:
            raise ValueError("JARVIS_SERVER_URL is required")
        if not self.device_id:
            raise ValueError("JARVIS_DEVICE_ID is required")
        if not self.device_token:
            raise ValueError("JARVIS_DEVICE_TOKEN is required")
