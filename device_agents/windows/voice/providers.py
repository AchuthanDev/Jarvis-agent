"""Provider interfaces for voice components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioData:
    samples: object
    sample_rate: int

    @property
    def has_audio(self) -> bool:
        try:
            return len(self.samples) > 0  # type: ignore[arg-type]
        except TypeError:
            return False


class STTProvider(Protocol):
    async def transcribe(self, audio: AudioData) -> str:
        """Return a transcript for one utterance."""


class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Return encoded audio bytes for text."""


class WakeWordProvider(Protocol):
    async def wait_for_wake_word(self) -> None:
        """Block until the configured wake word is detected."""


class VADProvider(Protocol):
    def is_speech(self, frame: object) -> bool:
        """Return whether a frame contains speech."""
