"""``current_time`` — current date/time on the server."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.tools.base import RISK_READ_ONLY, Tool, ToolContext


async def _current_time(tz: str | None = None, *, context: ToolContext) -> str:
    del context  # unused
    zone = ZoneInfo(tz) if tz else None
    now = datetime.now(zone)
    label = now.astimezone().tzname() or "local"
    if tz:
        return f"It is {now.isoformat(timespec='seconds')} ({tz})."
    return f"It is {now.isoformat(timespec='seconds')} ({label})."


def current_time_tool() -> Tool:
    return Tool(
        name="current_time",
        description=(
            "Current date and time on the JARVIS server. Use this instead of guessing "
            "the time or date."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tz": {
                    "type": "string",
                    "description": "Optional IANA timezone name (e.g. Europe/Berlin).",
                }
            },
            "additionalProperties": False,
        },
        fn=_current_time,
        risk=RISK_READ_ONLY,
        timeout=5.0,
    )
