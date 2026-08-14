"""System prompt construction for tool-using turns."""

from __future__ import annotations

from core.conversation.system_prompt import build_system_prompt
from core.tools.registry import ToolRegistry

_TOOL_INSTRUCTIONS = """\
TOOLS
You have access to tools. When you need information you do not already have,
request exactly one tool by replying with ONLY a single JSON object — no
markdown, no explanation, nothing else:

{"tool": "tool.name", "arguments": {"param": "value"}}

Rules:
- Request ONE tool per message. After the tool's result is shown to you, you may
  request another tool or answer.
- Only request tools from the list below. Never invent a tool name.
- Do not ask to use a tool for things you already know.
- Once you have what you need, reply normally in natural language.

Available tools:
{tools}
"""


def build_agent_prompt(registry: ToolRegistry | None) -> str:
    """Persona + tool-call protocol instructions + tool catalogue."""
    base = build_system_prompt()
    if registry is None or not registry.names():
        return base + "\n\n(No tools are available right now.)"
    # Use replace() — the template's JSON examples contain literal braces that
    # .format() would interpret as field names.
    return base + "\n\n" + _TOOL_INSTRUCTIONS.replace("{tools}", registry.describe())
