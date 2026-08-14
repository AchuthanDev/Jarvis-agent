"""Agent: the tool-using reasoning loop (understand → plan → act → observe → respond)."""

from core.agent.loop import (
    MAX_TOOL_ITERATIONS,
    AgentResult,
    format_result_for_model,
    run_agent_turn,
)
from core.agent.parsing import ToolRequest, parse_tool_request
from core.agent.prompt import build_agent_prompt

__all__ = [
    "MAX_TOOL_ITERATIONS",
    "AgentResult",
    "ToolRequest",
    "build_agent_prompt",
    "format_result_for_model",
    "parse_tool_request",
    "run_agent_turn",
]
