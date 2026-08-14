"""Tool error hierarchy.

Lives in its own module so ``base`` and ``validation`` can both import it
without a circular dependency.
"""


class ToolError(Exception):
    """Base error raised while handling a tool."""


class ToolExecutionError(ToolError):
    """The tool function itself failed."""


class ToolValidationError(ToolError):
    """The arguments do not match the tool's parameter schema."""
