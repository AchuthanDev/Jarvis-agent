"""Audio device listing, energy VAD, and push-to-talk recording."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from device_agents.windows.voice.providers import AudioData


@dataclass(frozen=True, slots=True)
class AudioDevice:
    index: int
    name: str
    channels: int
    default_samplerate: float


def _sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice is not installed. Run .\\install-voice.ps1 first."
        ) from exc
    return sd


def list_audio_devices() -> tuple[list[AudioDevice], list[AudioDevice]]:
    sd = _sounddevice()
    devices = sd.query_devices()
    inputs: list[AudioDevice] = []
    outputs: list[AudioDevice] = []
    for index, raw in enumerate(devices):
        device = dict(raw)
        name = str(device.get("name", f"Device {index}"))
        samplerate = float(device.get("default_samplerate") or 0)
        input_channels = int(device.get("max_input_channels") or 0)
        output_channels = int(device.get("max_output_channels") or 0)
        if input_channels > 0:
            inputs.append(AudioDevice(index, name, input_channels, samplerate))
        if output_channels > 0:
            outputs.append(AudioDevice(index, name, output_channels, samplerate))
    return inputs, outputs


class EnergyVAD:
    """Simple local VAD based on RMS energy.

    This is intentionally replaceable. It is enough for push-to-talk validation
    and avoids adding another model before the core voice path is proven.
    """

    def __init__(self, *, threshold: float = 0.012) -> None:
        self.threshold = threshold

    def is_speech(self, frame: object) -> bool:
        import numpy as np

        values = np.asarray(frame, dtype=np.float32)
        if values.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(values))))
        return rms >= self.threshold


class AudioRecorder:
    def __init__(
        self,
        *,
        sample_rate: int,
        input_device: str = "",
        vad: EnergyVAD | None = None,
        silence_seconds: float = 1.0,
        no_speech_timeout_seconds: float = 8.0,
        max_record_seconds: float = 30.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.input_device = input_device
        self.vad = vad or EnergyVAD()
        self.silence_seconds = silence_seconds
        self.no_speech_timeout_seconds = no_speech_timeout_seconds
        self.max_record_seconds = max_record_seconds

    async def record_until_silence(self) -> AudioData:
        return await asyncio.to_thread(self._record_blocking)

    def _record_blocking(self) -> AudioData:
        import numpy as np

        sd = _sounddevice()
        block_seconds = 0.1
        block_size = max(1, int(self.sample_rate * block_seconds))
        frames: list[Any] = []
        speech_started = False
        last_speech_at: float | None = None
        started_at = time.monotonic()
        device = self._device_argument(self.input_device)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=device,
            blocksize=block_size,
        ) as stream:
            while True:
                frame, _overflowed = stream.read(block_size)
                now = time.monotonic()
                is_speech = self.vad.is_speech(frame)
                if is_speech:
                    speech_started = True
                    last_speech_at = now
                if speech_started:
                    frames.append(frame.copy())
                if not speech_started and now - started_at >= self.no_speech_timeout_seconds:
                    return AudioData(samples=np.array([], dtype=np.float32), sample_rate=self.sample_rate)
                if speech_started and last_speech_at is not None:
                    if now - last_speech_at >= self.silence_seconds:
                        break
                if now - started_at >= self.max_record_seconds:
                    break

        if not frames:
            return AudioData(samples=np.array([], dtype=np.float32), sample_rate=self.sample_rate)
        audio = np.concatenate(frames, axis=0).reshape(-1)
        return AudioData(samples=audio, sample_rate=self.sample_rate)

    @staticmethod
    def _device_argument(value: str) -> int | str | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value
