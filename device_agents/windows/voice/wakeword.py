"""Wake-word provider scaffolding.

Phase 5 stops at push-to-talk validation. This module defines the replaceable
interface and a placeholder implementation so wake-word mode can be wired after
the microphone/STT/TTS path is proven on the real laptop.
"""

from __future__ import annotations

import asyncio


class NotImplementedWakeWord:
    def __init__(self, *, phrase: str = "hey jarvis") -> None:
        self.phrase = phrase

    async def wait_for_wake_word(self) -> None:
        raise RuntimeError(
            "Wake-word mode is not enabled in this milestone. Validate push-to-talk first."
        )


class KeyboardWakeWord:
    """Development provider that treats Enter as wake detection."""

    async def wait_for_wake_word(self) -> None:
        await asyncio.to_thread(input, "Press Enter to simulate wake word...")
