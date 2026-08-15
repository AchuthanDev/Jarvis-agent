"""Voice client orchestration for Windows."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from device_agents.windows.voice.audio import AudioRecorder
from device_agents.windows.voice.config import VoiceConfig
from device_agents.windows.voice.providers import STTProvider, TTSProvider
from device_agents.windows.voice.state import VoiceState, VoiceStateMachine
from device_agents.windows.voice.tts import PlaybackController


@dataclass(slots=True)
class ChatReply:
    conversation_id: str
    reply: str
    tool_calls: list[dict[str, Any]]


class JarvisChatClient:
    def __init__(self, config: VoiceConfig) -> None:
        config.validate_for_chat()
        self.config = config

    async def send_transcript(
        self,
        transcript: str,
        *,
        conversation_id: str | None = None,
    ) -> ChatReply:
        return await asyncio.to_thread(
            self._send_blocking,
            transcript,
            conversation_id,
        )

    def _send_blocking(self, transcript: str, conversation_id: str | None) -> ChatReply:
        payload: dict[str, Any] = {
            "message": transcript,
            "source": "voice",
            "source_device_id": self.config.device_id,
            "response_mode": self.config.response_mode,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.config.server_url}/api/chat",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-JARVIS-DEVICE-TOKEN": self.config.device_token,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"JARVIS server returned {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError("I can't reach the JARVIS server.") from exc
        return ChatReply(
            conversation_id=str(body["conversation_id"]),
            reply=str(body.get("message") or body.get("reply") or ""),
            tool_calls=list(body.get("tool_calls") or []),
        )


class VoiceInteraction:
    def __init__(
        self,
        *,
        recorder: AudioRecorder,
        stt: STTProvider,
        tts: TTSProvider,
        playback: PlaybackController,
        chat: JarvisChatClient,
        state: VoiceStateMachine | None = None,
    ) -> None:
        self.recorder = recorder
        self.stt = stt
        self.tts = tts
        self.playback = playback
        self.chat = chat
        self.state = state or VoiceStateMachine()
        self.conversation_id: str | None = None
        self.last_reply = ""

    async def push_to_talk_once(self) -> ChatReply | None:
        self.state.transition(VoiceState.LISTENING)
        print("Recording... speak now.")
        audio = await self.recorder.record_until_silence()
        self.state.transition(VoiceState.TRANSCRIBING)
        if not audio.has_audio:
            print("No speech detected. Returning to standby.")
            self.state.transition(VoiceState.IDLE)
            return None
        started = time.perf_counter()
        transcript = await self.stt.transcribe(audio)
        transcription_duration = time.perf_counter() - started
        print(f"transcription_duration={transcription_duration:.2f}s")
        if not transcript:
            print("I couldn't understand that.")
            self.state.transition(VoiceState.IDLE)
            return None
        print(f"You: {transcript}")

        if transcript.strip().lower() in {"jarvis stop", "stop", "stop talking"}:
            await self.playback.stop()
            print("Stopped.")
            self.state.transition(VoiceState.IDLE)
            return None

        self.state.transition(VoiceState.PROCESSING)
        agent_started = time.perf_counter()
        reply = await self.chat.send_transcript(
            transcript,
            conversation_id=self.conversation_id,
        )
        agent_duration = time.perf_counter() - agent_started
        self.conversation_id = reply.conversation_id
        self.last_reply = reply.reply
        print(f"agent_duration={agent_duration:.2f}s")
        for call in reply.tool_calls:
            print(f"tool_call={call.get('tool')} status={call.get('status')}")
        print(f"JARVIS: {reply.reply}")

        self.state.transition(VoiceState.SPEAKING)
        try:
            tts_started = time.perf_counter()
            speech = await self.tts.synthesize(reply.reply)
            await self.playback.play(speech)
            print(f"tts_duration={time.perf_counter() - tts_started:.2f}s")
        except Exception as exc:  # noqa: BLE001 - text response remains available
            print(f"TTS unavailable: {exc}")
        finally:
            self.state.transition(VoiceState.IDLE)
        return reply
