"""Command-line entry point for the Windows voice client."""

from __future__ import annotations

import argparse
import asyncio

from device_agents.windows.voice.audio import AudioRecorder, EnergyVAD, list_audio_devices
from device_agents.windows.voice.client import JarvisChatClient, VoiceInteraction
from device_agents.windows.voice.config import VoiceConfig
from device_agents.windows.voice.stt import create_stt_provider
from device_agents.windows.voice.tts import PlaybackController, create_tts_provider


def _print_devices() -> None:
    inputs, outputs = list_audio_devices()
    print("Input devices:")
    for device in inputs:
        print(f"[{device.index}] {device.name} ({device.channels} ch, {device.default_samplerate:g} Hz)")
    print("")
    print("Output devices:")
    for device in outputs:
        print(f"[{device.index}] {device.name} ({device.channels} ch, {device.default_samplerate:g} Hz)")


def _build_interaction(config: VoiceConfig) -> VoiceInteraction:
    recorder = AudioRecorder(
        sample_rate=config.sample_rate,
        input_device=config.audio_input_device,
        vad=EnergyVAD(threshold=config.vad_threshold),
        silence_seconds=config.silence_seconds,
        no_speech_timeout_seconds=config.no_speech_timeout_seconds,
        max_record_seconds=config.max_record_seconds,
    )
    return VoiceInteraction(
        recorder=recorder,
        stt=create_stt_provider(config.stt_provider, model_name=config.stt_model),
        tts=create_tts_provider(config.tts_provider, voice=config.tts_voice),
        playback=PlaybackController(output_device=config.audio_output_device),
        chat=JarvisChatClient(config),
    )


async def _push_to_talk(config: VoiceConfig, *, once: bool = False) -> None:
    interaction = _build_interaction(config)
    print("JARVIS Voice Client")
    print(f"Server: {config.server_url}")
    print(f"Device: {config.device_name}")
    print("Mode: push-to-talk")
    print("")
    while True:
        await asyncio.to_thread(input, "Press Enter, speak, then pause...")
        await interaction.push_to_talk_once()
        if once:
            return


async def _test_tts(config: VoiceConfig, text: str) -> None:
    tts = create_tts_provider(config.tts_provider, voice=config.tts_voice)
    playback = PlaybackController(output_device=config.audio_output_device)
    print(f"JARVIS: {text}")
    await playback.play(await tts.synthesize(text))


async def _test_mic(config: VoiceConfig) -> None:
    recorder = AudioRecorder(
        sample_rate=config.sample_rate,
        input_device=config.audio_input_device,
        vad=EnergyVAD(threshold=config.vad_threshold),
        silence_seconds=config.silence_seconds,
        no_speech_timeout_seconds=config.no_speech_timeout_seconds,
        max_record_seconds=10.0,
    )
    print("Recording test. Speak now.")
    audio = await recorder.record_until_silence()
    print(f"Captured samples: {len(audio.samples) if audio.has_audio else 0}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JARVIS Windows voice client")
    parser.add_argument("--config", default=None, help="Path to Windows agent .env")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--push-to-talk", action="store_true")
    parser.add_argument("--wake-word", action="store_true")
    parser.add_argument("--test-mic", action="store_true")
    parser.add_argument("--test-tts", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one push-to-talk cycle")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = VoiceConfig.load(args.config)
    if args.list_devices:
        _print_devices()
    elif args.test_tts:
        asyncio.run(_test_tts(config, "JARVIS voice output is ready."))
    elif args.test_mic:
        asyncio.run(_test_mic(config))
    elif args.push_to_talk:
        asyncio.run(_push_to_talk(config, once=args.once))
    elif args.wake_word:
        raise SystemExit("Wake-word mode is scaffolded but intentionally blocked until push-to-talk passes.")
    else:
        raise SystemExit("Choose --list-devices, --test-mic, --test-tts, or --push-to-talk")


if __name__ == "__main__":
    main()
