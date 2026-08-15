"""Shared device protocol constants and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse

WINDOWS_TOOL_PREFIX = "windows."

WINDOWS_ACTION_TO_TOOL = {
    "open_url": "windows.open_url",
    "open_app": "windows.open_app",
    "notification": "windows.notification",
    "system_info": "windows.system_info",
}
WINDOWS_TOOL_TO_ACTION = {tool: action for action, tool in WINDOWS_ACTION_TO_TOOL.items()}

SAFE_URL_SCHEMES = {"http", "https"}

KNOWN_WEBSITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
}


@dataclass(frozen=True, slots=True)
class NormalizedWindowsCommand:
    tool: str
    action: str


def normalize_windows_command(name: str) -> NormalizedWindowsCommand:
    """Accept either the public tool name or device-local action name."""
    value = name.strip()
    if not value:
        raise ValueError("command name must not be empty")
    if value in WINDOWS_TOOL_TO_ACTION:
        return NormalizedWindowsCommand(tool=value, action=WINDOWS_TOOL_TO_ACTION[value])
    if value in WINDOWS_ACTION_TO_TOOL:
        return NormalizedWindowsCommand(tool=WINDOWS_ACTION_TO_TOOL[value], action=value)
    raise ValueError(f"unsupported Windows command {name!r}")


def validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in SAFE_URL_SCHEMES:
        raise ValueError("only http and https URLs are allowed")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname")
    return url


def normalize_website_url(value: str) -> str:
    """Normalize a safe user/site URL into an http(s) URL."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("URL must not be empty")
    known = KNOWN_WEBSITES.get(candidate.lower().removesuffix(".com"))
    if known:
        return known
    parsed = urlparse(candidate)
    if parsed.scheme:
        return validate_http_url(candidate)
    if "." in candidate and not any(char.isspace() for char in candidate):
        return validate_http_url(f"https://{candidate}")
    raise ValueError("Provide a valid website name or http/https URL")


def google_search_url(query: str) -> str:
    clean = query.strip()
    if not clean:
        raise ValueError("search query must not be empty")
    return f"https://www.google.com/search?q={quote_plus(clean)}"


def sanitized_parameters(tool: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Return audit-safe device command parameters.

    Current Windows tools do not accept secrets, but this centralizes redaction
    for future capabilities.
    """
    if tool == "windows.notification":
        return {
            "title": parameters.get("title"),
            "message": parameters.get("message"),
        }
    return dict(parameters)
