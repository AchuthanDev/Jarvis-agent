"""Parsing of tool requests from LLM output.

The agent uses a JSON tool-call protocol that works uniformly across every
provider (OpenAI-compatible, Gemini, Ollama). The LLM is instructed to emit a
single JSON object — ``{"tool": "...", "arguments": {...}}`` — when it wants to
use a tool, and natural language otherwise. Parsing is deliberately lenient.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class ToolRequest:
    name: str
    arguments: dict[str, Any]


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Return the first balanced JSON object found in ``text``, or ``None``."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_tool_request(response: str) -> ToolRequest | None:
    """Parse ``response`` into a :class:`ToolRequest`, or ``None`` for prose.

    Only responses that are (after fence-stripping) a single JSON object with a
    ``tool`` string key are treated as tool requests.
    """
    candidate = _strip_fences(response)
    if not candidate.startswith("{"):
        return None
    data = _extract_json_object(candidate)
    if not isinstance(data, dict):
        return None
    name = data.get("tool")
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolRequest(name=name.strip(), arguments=arguments)
