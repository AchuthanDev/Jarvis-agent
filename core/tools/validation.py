"""Argument validation against JSON Schema (draft 2020-12)."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from core.tools.errors import ToolValidationError


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Raise :class:`ToolValidationError` when ``arguments`` violate ``schema``."""
    if not schema:
        if arguments:
            raise ToolValidationError(f"unexpected arguments: {list(arguments)}")
        return
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(arguments), key=lambda err: err.path)
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.path) or "(root)"
        raise ToolValidationError(f"invalid argument {path!r}: {first.message}")
