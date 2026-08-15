"""Explicit voice interaction state machine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class VoiceState(str, Enum):
    IDLE = "IDLE"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"


@dataclass(slots=True)
class VoiceStateMachine:
    state: VoiceState = VoiceState.IDLE

    def transition(self, new_state: VoiceState) -> None:
        old_state = self.state
        self.state = new_state
        logger.info(
            "voice_state_transition",
            extra={"old_state": old_state.value, "new_state": new_state.value},
        )
