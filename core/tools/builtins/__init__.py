"""Built-in tools shipped with JARVIS.

``register_default_tools`` is called once at application startup; the app owns
the resulting registry instance.
"""

from __future__ import annotations

from core.tools.base import Tool as Tool
from core.tools.builtins.memory_tools import build_memory_tools
from core.tools.builtins.system_status import system_status_tool
from core.tools.builtins.time_tool import current_time_tool
from core.tools.builtins.web_search import web_search_tool
from core.tools.builtins.windows_tools import build_windows_tools
from core.tools.registry import ToolRegistry


def register_default_tools(registry: ToolRegistry) -> None:
    """Register every built-in tool on ``registry``."""
    for tool in (
        current_time_tool(),
        system_status_tool(),
        web_search_tool(),
        *build_memory_tools(),
        *build_windows_tools(),
    ):
        registry.register(tool)
