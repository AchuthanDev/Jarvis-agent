"""Unit tests for the Windows voice client without real audio hardware."""

from __future__ import annotations

import json

import pytest

from device_agents.windows.voice.audio import EnergyVAD
from device_agents.windows.voice.client import ChatReply, JarvisChatClient, VoiceInteraction
from device_agents.windows.voice.config import VoiceConfig
from device_agents.windows.voice.providers import AudioData
from device_agents.windows.voice.state import VoiceState, VoiceStateMachine
from device_agents.windows.voice.stt import NullSTT, create_stt_provider
from device_agents.windows.voice.tts import NullTTS, PlaybackController, create_tts_provider


def test_voice_config_loads_from_env_file(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / ".env"
    config_file.write_text(
        "\n".join(
            [
                "JARVIS_SERVER_URL=http://jarvis.local:8000",
                "JARVIS_DEVICE_ID=device-id",
                "JARVIS_DEVICE_TOKEN=device-token",
                "JARVIS_DEVICE_NAME=My-Laptop",
                "JARVIS_STT_PROVIDER=null",
                "JARVIS_TTS_PROVIDER=null",
                "JARVIS_AUDIO_INPUT_DEVICE=1",
            ]
        ),
        encoding="utf-8",
    )
    for key in (
        "JARVIS_SERVER_URL",
        "JARVIS_DEVICE_ID",
        "JARVIS_DEVICE_TOKEN",
        "JARVIS_DEVICE_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    config = VoiceConfig.load(config_file)

    assert config.server_url == "http://jarvis.local:8000"
    assert config.device_id == "device-id"
    assert config.audio_input_device == "1"


def test_voice_config_requires_registered_device() -> None:
    config = VoiceConfig(
        server_url="http://jarvis.local:8000",
        device_id="",
        device_token="",
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

    with pytest.raises(ValueError, match="JARVIS_DEVICE_ID"):
        config.validate_for_chat()


def test_energy_vad_detects_speech() -> None:
    import numpy as np

    vad = EnergyVAD(threshold=0.01)
    assert vad.is_speech(np.array([0.0, 0.02, -0.02], dtype=np.float32)) is True
    assert vad.is_speech(np.array([0.0, 0.001, -0.001], dtype=np.float32)) is False


def test_voice_state_machine_transitions() -> None:
    state = VoiceStateMachine()
    state.transition(VoiceState.LISTENING)
    state.transition(VoiceState.TRANSCRIBING)

    assert state.state == VoiceState.TRANSCRIBING


@pytest.mark.asyncio
async def test_null_stt_and_tts_interfaces() -> None:
    stt = NullSTT("Open Google on my laptop.")
    tts = NullTTS()

    transcript = await stt.transcribe(AudioData(samples=[1, 2, 3], sample_rate=16000))
    speech = await tts.synthesize("Done.")

    assert transcript == "Open Google on my laptop."
    assert speech == b"Done."


def test_provider_factories_reject_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported STT"):
        create_stt_provider("bad", model_name="base")
    with pytest.raises(ValueError, match="Unsupported TTS"):
        create_tts_provider("bad", voice="")


@pytest.mark.asyncio
async def test_playback_stop_marks_not_playing() -> None:
    playback = PlaybackController()
    playback._playing = True

    await playback.stop()

    assert playback.is_playing is False


@pytest.mark.asyncio
async def test_chat_client_sends_voice_metadata(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "conversation_id": "conversation-id",
                    "message": "Google is open on your laptop.",
                    "tool_calls": [{"tool": "windows.open_url", "status": "executed"}],
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("device_agents.windows.voice.client.request.urlopen", fake_urlopen)
    config = VoiceConfig(
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

    reply = await JarvisChatClient(config).send_transcript("Open Google on my laptop.")

    assert captured["url"] == "http://jarvis.local:8000/api/chat"
    assert captured["headers"]["X-jarvis-device-token"] == "device-token"
    assert captured["payload"]["source"] == "voice"
    assert captured["payload"]["source_device_id"] == "device-id"
    assert captured["payload"]["response_mode"] == "voice"
    assert reply.conversation_id == "conversation-id"


@pytest.mark.asyncio
async def test_chat_client_reports_server_unavailable(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        del req, timeout
        raise OSError("connection refused")

    monkeypatch.setattr("device_agents.windows.voice.client.request.urlopen", fake_urlopen)
    config = VoiceConfig(
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

    with pytest.raises(RuntimeError, match="can't reach"):
        await JarvisChatClient(config).send_transcript("Hello")


@pytest.mark.asyncio
async def test_voice_interaction_reuses_conversation_id() -> None:
    class FakeRecorder:
        async def record_until_silence(self) -> AudioData:
            return AudioData(samples=[1], sample_rate=16000)

    class FakeSTT:
        def __init__(self) -> None:
            self.transcripts = ["How much RAM is my laptop using?", "What about CPU?"]

        async def transcribe(self, audio: AudioData) -> str:
            assert audio.has_audio is True
            return self.transcripts.pop(0)

    class FakeChat:
        def __init__(self) -> None:
            self.conversation_ids: list[str | None] = []

        async def send_transcript(
            self, transcript: str, *, conversation_id: str | None = None
        ) -> ChatReply:
            del transcript
            self.conversation_ids.append(conversation_id)
            return ChatReply(conversation_id="conversation-1", reply="Done.", tool_calls=[])

    class FakePlayback:
        async def play(self, audio: bytes) -> None:
            assert audio == b"Done."

        async def stop(self) -> None:
            pass

    chat = FakeChat()
    interaction = VoiceInteraction(
        recorder=FakeRecorder(),
        stt=FakeSTT(),
        tts=NullTTS(),
        playback=FakePlayback(),
        chat=chat,
    )

    await interaction.push_to_talk_once()
    await interaction.push_to_talk_once()

    assert chat.conversation_ids == [None, "conversation-1"]
