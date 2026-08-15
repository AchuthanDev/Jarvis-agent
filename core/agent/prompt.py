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
- For Windows actions, do not say the action is done until the tool result says it
  executed successfully.
- If the user says "my laptop", "laptop", "PC", or "computer", pass that phrase as
  device_name when useful; the tool resolves aliases/defaults.
- For "Open Google", call windows.open_url with {"url": "Google"} or the full
  https URL. For "Search Google for X", call windows.open_url with
  {"search_query": "X"}.
- For "Open VS Code/Chrome/Edge/Notepad/Calculator", call windows.open_app with the
  app alias, such as "vscode" or "chrome".
- For RAM/CPU/battery/disk/IP/uptime questions about a laptop, call
  windows.system_info, then answer only the relevant part.
- For follow-ups like "What about CPU?" reuse the same topic/device from the recent
  conversation when it is clear.

Available tools:
{tools}
"""

_VOICE_RESPONSE_INSTRUCTIONS = """\

VOICE RESPONSE MODE
The user's request came from a voice endpoint. Keep final spoken responses short,
natural, and suitable for text-to-speech. Do not dump raw JSON unless the user
explicitly asks for it.
"""

def build_agent_prompt(registry: ToolRegistry | None, *, response_mode: str = "text") -> str:
    """Persona + tool-call protocol instructions + tool catalogue."""
    base = build_system_prompt()
    if registry is None or not registry.names():
        prompt = base + "\n\n(No tools are available right now.)"
    else:
        # Use replace() — the template's JSON examples contain literal braces that
        # .format() would interpret as field names.
        prompt = base + "\n\n" + _TOOL_INSTRUCTIONS.replace("{tools}", registry.describe())
    if response_mode == "voice":
        prompt += "\n\n" + _VOICE_RESPONSE_INSTRUCTIONS
    return prompt
