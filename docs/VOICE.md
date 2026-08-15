# Voice

Phase 5 adds a Windows voice client that calls the existing JARVIS chat/agent API.
Voice does not contain command routing or business logic.

```text
microphone -> VAD -> STT -> POST /api/chat -> existing agent/tools -> TTS -> speaker
```

## Current Milestone

Push-to-talk is implemented for Windows and ready for manual validation.
Wake-word mode is scaffolded but intentionally blocked until push-to-talk passes.

## Architecture

Windows voice code lives under `device_agents/windows/voice/`:

| Module | Purpose |
|---|---|
| `config.py` | Loads `.env` voice/audio settings. |
| `audio.py` | Lists devices, records audio, energy VAD. |
| `stt.py` | STT provider interface and `faster_whisper` provider. |
| `tts.py` | TTS provider interface, `edge_tts`, cancellable playback. |
| `client.py` | Sends transcripts to `/api/chat` and preserves `conversation_id`. |
| `state.py` | Explicit voice state machine. |
| `wakeword.py` | Replaceable wake-word scaffolding. |
| `cli.py` | Windows voice command-line entry point. |

The Debian API does not process raw audio in this milestone.

## Providers

Selected initial providers:

```text
STT: faster_whisper
TTS: edge_tts
VAD: local energy VAD
```

These are replaceable through provider interfaces. Voice dependencies are installed
only on the Windows endpoint via `requirements-voice.txt`.

## Privacy

Push-to-talk records only after the user presses Enter. Wake-word mode is not active
yet. With the default provider, STT runs locally on Windows through faster-whisper.
Edge TTS sends response text to Microsoft Edge TTS. Raw audio is not stored by default.

## Windows Setup

From `device_agents/windows` on the laptop:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
.\install-voice.ps1
```

Confirm `.env` contains the registered device identity:

```env
JARVIS_SERVER_URL=http://<debian-lan-ip>:8000
JARVIS_DEVICE_ID=<registered-device-id>
JARVIS_DEVICE_TOKEN=<registered-device-token>
JARVIS_DEVICE_NAME=My-Laptop
```

Voice settings:

```env
JARVIS_VOICE_ENABLED=true
JARVIS_STT_PROVIDER=faster_whisper
JARVIS_STT_MODEL=base
JARVIS_TTS_PROVIDER=edge_tts
JARVIS_TTS_VOICE=en-US-GuyNeural
JARVIS_AUDIO_INPUT_DEVICE=
JARVIS_AUDIO_OUTPUT_DEVICE=
JARVIS_VAD_ENABLED=true
```

## Audio Devices

List devices:

```powershell
.\voice.ps1 --list-devices
```

Use a device index or device name:

```env
JARVIS_AUDIO_INPUT_DEVICE=1
JARVIS_AUDIO_OUTPUT_DEVICE=0
```

Leave blank to use the OS default.

## Manual Tests

Test microphone:

```powershell
.\voice.ps1 --test-mic
```

Test TTS:

```powershell
.\voice.ps1 --test-tts
```

Start push-to-talk:

```powershell
.\voice.ps1 --push-to-talk
```

First acceptance utterance:

```text
Open Google on my laptop.
```

Expected console:

```text
Recording... speak now.
You: Open Google on my laptop.
tool_call=windows.open_url status=executed
JARVIS: Google is open on your laptop.
```

Google must actually open on the Windows laptop, and the reply should be spoken.

Additional utterances:

```text
How much RAM is my laptop using?
Open VS Code.
```

The same `conversation_id` is reused by the voice client for follow-up context.

## Wake Word

`.\voice.ps1 --wake-word` currently exits with a clear message. The state-machine and
provider interface exist, but wake-word detection should be enabled only after the
push-to-talk path passes on the real laptop.

## Troubleshooting

No microphone:

```text
No microphone is available.
```

Run `.\voice.ps1 --list-devices` and configure `JARVIS_AUDIO_INPUT_DEVICE`.

STT failure:

```text
I couldn't understand that.
```

Try a quieter room or a lower `JARVIS_VAD_THRESHOLD`.

Server unavailable:

```text
I can't reach the JARVIS server.
```

Verify `JARVIS_SERVER_URL` and `curl http://<server>:8000/api/health/ready`.

TTS unavailable:

The client still prints the JARVIS response and reports the TTS error.
