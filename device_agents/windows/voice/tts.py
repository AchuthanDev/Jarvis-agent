"""Text-to-speech providers and cancellable playback."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from device_agents.windows.voice.providers import TTSProvider


class EdgeTTS:
    def __init__(self, *, voice: str = "en-US-GuyNeural") -> None:
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge-tts is not installed. Run .\\install-voice.ps1 first.") from exc
        communicate = edge_tts.Communicate(text=text, voice=self.voice)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)


class NullTTS:
    async def synthesize(self, text: str) -> bytes:
        return text.encode("utf-8")


class PlaybackController:
    def __init__(self, *, output_device: str = "") -> None:
        self.output_device = output_device
        self._lock = asyncio.Lock()
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def play(self, audio: bytes, *, suffix: str = ".mp3") -> None:
        if not audio:
            return
        async with self._lock:
            await self.stop()
            self._playing = True
            try:
                await asyncio.to_thread(self._play_blocking, audio, suffix)
            finally:
                self._playing = False

    async def stop(self) -> None:
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except ImportError:
            pass
        self._playing = False

    def _play_blocking(self, audio: bytes, suffix: str) -> None:
        try:
            import pygame
        except ImportError as exc:
            raise RuntimeError("pygame is not installed. Run .\\install-voice.ps1 first.") from exc
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio)
            temp_path = Path(temp_file.name)
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(devicename=self.output_device or None)
            pygame.mixer.music.load(str(temp_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def create_tts_provider(provider: str, *, voice: str) -> TTSProvider:
    normalized = provider.strip().lower()
    if normalized == "edge_tts":
        return EdgeTTS(voice=voice)
    if normalized == "null":
        return NullTTS()
    raise ValueError(f"Unsupported TTS provider: {provider}")
