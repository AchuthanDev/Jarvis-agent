"""Direct Windows device command tester for Phase 4 validation.

This bypasses the LLM and calls the authenticated device command API directly.
Use it to separate device communication failures from agent/tool-selection
problems.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib import error, request


def _json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        token = token.strip()
        if "\n" in token or "\r" in token:
            raise SystemExit(
                "Admin token contains multiple lines. Use ADMIN_API_TOKEN or pass --admin-token explicitly."
            )
        headers["X-JARVIS-ADMIN-TOKEN"] = token
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API returned {exc.code}: {body}") from exc


def _resolve_device(base_url: str, device: str) -> str:
    devices = _json_request("GET", f"{base_url}/api/devices")
    assert isinstance(devices, list)
    for item in devices:
        if item["id"] == device or item["name"].lower() == device.lower():
            return str(item["id"])
    names = ", ".join(f"{item['name']} ({item['id']})" for item in devices)
    raise SystemExit(f"Device not found: {device}. Registered devices: {names or '(none)'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test a JARVIS Windows device tool")
    parser.add_argument(
        "--server",
        default=os.environ.get("JARVIS_SERVER_URL", "http://127.0.0.1:8000"),
        help="JARVIS server URL",
    )
    parser.add_argument(
        "--admin-token",
        default=os.environ.get("JARVIS_ADMIN_TOKEN") or os.environ.get("JARVIS_SECRET_KEY"),
        help="Direct command admin token",
    )
    parser.add_argument("--device", required=True, help="Device UUID or exact device name")
    parser.add_argument(
        "--tool",
        required=True,
        choices=[
            "windows.open_url",
            "windows.open_app",
            "windows.notification",
            "windows.system_info",
        ],
    )
    parser.add_argument("--url", help="URL for windows.open_url")
    parser.add_argument("--app", help="Application alias for windows.open_app")
    parser.add_argument("--title", default="JARVIS", help="Notification title")
    parser.add_argument("--message", default="Hello from JARVIS.", help="Notification message")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.admin_token:
        raise SystemExit("Set --admin-token or JARVIS_ADMIN_TOKEN/JARVIS_SECRET_KEY")

    base_url = args.server.rstrip("/")
    device_id = _resolve_device(base_url, args.device)

    parameters: dict[str, Any]
    if args.tool == "windows.open_url":
        if not args.url:
            raise SystemExit("--url is required for windows.open_url")
        parameters = {"url": args.url}
    elif args.tool == "windows.open_app":
        if not args.app:
            raise SystemExit("--app is required for windows.open_app")
        parameters = {"app": args.app}
    elif args.tool == "windows.notification":
        parameters = {"title": args.title, "message": args.message}
    else:
        parameters = {}

    response = _json_request(
        "POST",
        f"{base_url}/api/devices/{device_id}/commands",
        token=args.admin_token,
        payload={"action": args.tool, "parameters": parameters},
    )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
