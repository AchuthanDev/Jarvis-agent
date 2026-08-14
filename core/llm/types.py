"""Shared value types for the LLM provider interface."""

from __future__ import annotations

from dataclasses import dataclass, field

MESSAGE_ROLES = ("system", "user", "assistant", "tool")


@dataclass(slots=True)
class ChatMessage:
    """A single message in the conversation passed to an LLM."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in MESSAGE_ROLES:
            raise ValueError(f"invalid chat role: {self.role!r}")

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMResponse:
    """A non-streamed model response."""

    content: str
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
