"""Speech-to-text providers for the Windows voice client."""

from __future__ import annotations

import asyncio
import time

from device_agents.windows.voice.providers import AudioData, STTProvider


class FasterWhisperSTT:
    def __init__(self, *, model_name: str = "base") -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed. Run .\\install-voice.ps1 first."
                ) from exc
            self._model = WhisperModel(self.model_name, device="auto", compute_type="auto")
        return self._model

    async def transcribe(self, audio: AudioData) -> str:
        if not audio.has_audio:
            return ""
        started = time.perf_counter()
        text = await asyncio.to_thread(self._transcribe_blocking, audio)
        duration = time.perf_counter() - started
        print(f"Transcription completed in {duration:.2f}s.")
        return text

    def _transcribe_blocking(self, audio: AudioData) -> str:
        model = self._load_model()
        segments, _info = model.transcribe(
            audio.samples,
            language="en",
            vad_filter=False,
            beam_size=1,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class NullSTT:
    """Test double / fallback provider."""

    def __init__(self, transcript: str = "") -> None:
        self.transcript = transcript

    async def transcribe(self, audio: AudioData) -> str:
        del audio
        return self.transcript


def create_stt_provider(provider: str, *, model_name: str) -> STTProvider:
    normalized = provider.strip().lower()
    if normalized == "faster_whisper":
        return FasterWhisperSTT(model_name=model_name)
    if normalized == "null":
        return NullSTT()
    raise ValueError(f"Unsupported STT provider: {provider}")
