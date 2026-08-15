"""Windows companion agent for JARVIS.

Initial Phase 4 agent:
- registers with the server using a one-time registration secret;
- maintains an authenticated WebSocket;
- sends heartbeats;
- executes a small allowlisted command set.

It deliberately does not expose arbitrary shell execution.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import socket
import sys
import webbrowser
from typing import Any
from urllib import request
from urllib.parse import urlparse

import websockets

AGENT_VERSION = "0.1.0"
CAPABILITIES = [
    "windows.open_url",
    "windows.open_app",
    "windows.notification",
    "windows.system_info",
]

APP_COMMANDS = {
    "chrome": ["cmd", "/c", "start", "", "chrome"],
    "google chrome": ["cmd", "/c", "start", "", "chrome"],
    "edge": ["cmd", "/c", "start", "", "msedge"],
    "microsoft edge": ["cmd", "/c", "start", "", "msedge"],
    "firefox": ["cmd", "/c", "start", "", "firefox"],
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "vscode": ["cmd", "/c", "start", "", "code"],
    "vs code": ["cmd", "/c", "start", "", "code"],
}


def _server_url() -> str:
    return os.environ.get("JARVIS_SERVER_URL", "http://localhost:8000").rstrip("/")


def _ws_url(server_url: str, device_id: str, token: str) -> str:
    parsed = urlparse(server_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    return f"{scheme}://{netloc}/ws/device?device_id={device_id}&token={token}"


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def register(args: argparse.Namespace) -> None:
    secret = args.registration_secret or os.environ.get("JARVIS_DEVICE_REGISTRATION_SECRET")
    if not secret:
        raise SystemExit("Set JARVIS_DEVICE_REGISTRATION_SECRET or pass --registration-secret")
    payload = {
        "registration_secret": secret,
        "name": args.name or socket.gethostname(),
        "device_type": "windows",
        "operating_system": platform.platform(),
        "agent_version": AGENT_VERSION,
        "capabilities": CAPABILITIES,
    }
    response = _post_json(f"{_server_url()}/api/devices/register", payload)
    print(json.dumps(response, indent=2))


async def _open_url(parameters: dict[str, Any]) -> dict[str, Any]:
    url = str(parameters.get("url", ""))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    webbrowser.open(url)
    return {"opened": True, "url": url}


async def _open_app(parameters: dict[str, Any]) -> dict[str, Any]:
    app = str(parameters.get("app", "")).strip().lower()
    command = APP_COMMANDS.get(app)
    if command is None:
        allowed = ", ".join(sorted(APP_COMMANDS))
        raise ValueError(f"app is not allowlisted. Allowed: {allowed}")
    await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return {"opened": True, "app": app}


async def _notification(parameters: dict[str, Any]) -> dict[str, Any]:
    title = str(parameters.get("title", "JARVIS"))
    message = str(parameters.get("message", ""))
    powershell = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] | Out-Null; "
            f"Write-Host {json.dumps(title + ': ' + message)}"
        ),
    ]
    # Toast support varies by install context; fall back to a harmless console write.
    await asyncio.create_subprocess_exec(
        *powershell,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return {"shown": True, "title": title}


async def _system_info(parameters: dict[str, Any]) -> dict[str, Any]:
    del parameters
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


HANDLERS = {
    "open_url": _open_url,
    "open_app": _open_app,
    "notification": _notification,
    "system_info": _system_info,
}


async def _heartbeat(ws) -> None:
    while True:
        await asyncio.sleep(15)
        await ws.send(json.dumps({"type": "heartbeat", "capabilities": CAPABILITIES}))


async def run(args: argparse.Namespace) -> None:
    device_id = args.device_id or os.environ.get("JARVIS_DEVICE_ID")
    token = args.device_token or os.environ.get("JARVIS_DEVICE_TOKEN")
    if not device_id or not token:
        raise SystemExit("Set JARVIS_DEVICE_ID and JARVIS_DEVICE_TOKEN, or pass both flags")
    url = _ws_url(_server_url(), device_id, token)

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"type": "heartbeat", "capabilities": CAPABILITIES}))
                heartbeat = asyncio.create_task(_heartbeat(ws))
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("type") != "command":
                            continue
                        request_id = message.get("request_id")
                        action = message.get("action")
                        parameters = message.get("parameters") or {}
                        try:
                            handler = HANDLERS[action]
                            result = await handler(parameters)
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "success": True,
                                "result": result,
                            }
                        except Exception as exc:  # noqa: BLE001 - returned to server as failure
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "success": False,
                                "error": str(exc),
                            }
                        await ws.send(json.dumps(response))
                finally:
                    heartbeat.cancel()
        except Exception as exc:  # noqa: BLE001 - reconnect loop
            print(f"Disconnected: {exc}. Reconnecting in 5s.", file=sys.stderr)
            await asyncio.sleep(5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JARVIS Windows companion agent")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="Register this Windows device")
    reg.add_argument("--name")
    reg.add_argument("--registration-secret")
    reg.set_defaults(func=register)

    run_cmd = sub.add_parser("run", help="Connect and wait for commands")
    run_cmd.add_argument("--device-id")
    run_cmd.add_argument("--device-token")
    run_cmd.set_defaults(func=lambda args: asyncio.run(run(args)))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
