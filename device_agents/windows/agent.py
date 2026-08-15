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
import time
import webbrowser
from pathlib import Path
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

DEFAULT_CONFIG_FILE = Path(__file__).with_name(".env")
MAX_RECONNECT_DELAY = 60


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()
    existing.update(values)
    lines = [
        "# JARVIS Windows Agent configuration. Do not commit this file.",
        f"JARVIS_SERVER_URL={existing.get('JARVIS_SERVER_URL', '')}",
        f"JARVIS_DEVICE_ID={existing.get('JARVIS_DEVICE_ID', '')}",
        f"JARVIS_DEVICE_TOKEN={existing.get('JARVIS_DEVICE_TOKEN', '')}",
        f"JARVIS_DEVICE_NAME={existing.get('JARVIS_DEVICE_NAME', socket.gethostname())}",
        f"JARVIS_WINDOWS_APPS_JSON={existing.get('JARVIS_WINDOWS_APPS_JSON', '')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _config_file(args: argparse.Namespace | None = None) -> Path:
    value = (
        getattr(args, "config", None)
        or os.environ.get("JARVIS_CONFIG_FILE")
        or str(DEFAULT_CONFIG_FILE)
    )
    path = Path(value)
    return path.expanduser().resolve()


def _load_config(args: argparse.Namespace | None = None) -> Path:
    path = _config_file(args)
    _load_env_file(path)
    return path


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
    config_file = _load_config(args)
    if args.server_url:
        os.environ["JARVIS_SERVER_URL"] = args.server_url.rstrip("/")
    secret = args.registration_secret or os.environ.get("JARVIS_DEVICE_REGISTRATION_SECRET")
    if not secret:
        raise SystemExit("Set JARVIS_DEVICE_REGISTRATION_SECRET or pass --registration-secret")
    device_name = args.name or os.environ.get("JARVIS_DEVICE_NAME") or socket.gethostname()
    payload = {
        "registration_secret": secret,
        "name": device_name,
        "device_type": "windows",
        "operating_system": platform.platform(),
        "agent_version": AGENT_VERSION,
        "capabilities": CAPABILITIES,
    }
    response = _post_json(f"{_server_url()}/api/devices/register", payload)
    _write_env_file(
        config_file,
        {
            "JARVIS_SERVER_URL": _server_url(),
            "JARVIS_DEVICE_ID": response["device_id"],
            "JARVIS_DEVICE_TOKEN": response["device_token"],
            "JARVIS_DEVICE_NAME": device_name,
        },
    )
    print("Registered with JARVIS.")
    print(f"Device: {device_name}")
    print(f"Device ID: {response['device_id']}")
    print(f"Config: {config_file}")
    print("Token stored in config file and not printed.")


def _load_app_commands() -> dict[str, list[str]]:
    commands = {name: list(command) for name, command in APP_COMMANDS.items()}
    config = os.environ.get("JARVIS_WINDOWS_APPS_JSON")
    if not config:
        return commands
    path = Path(config).expanduser()
    if not path.exists():
        print(f"App registry not found: {path}", file=sys.stderr)
        return commands
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JARVIS_WINDOWS_APPS_JSON must contain a JSON object")
    for alias, command in data.items():
        if not isinstance(alias, str) or not isinstance(command, list):
            raise ValueError("app registry entries must map strings to string arrays")
        if not all(isinstance(part, str) and part for part in command):
            raise ValueError("app registry command arrays must contain non-empty strings")
        commands[alias.strip().lower()] = command
    return commands


async def _open_url(parameters: dict[str, Any]) -> dict[str, Any]:
    url = str(parameters.get("url", ""))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname")
    webbrowser.open(url)
    return {"opened": True, "url": url}


async def _open_app(parameters: dict[str, Any]) -> dict[str, Any]:
    app = str(parameters.get("app", "")).strip().lower()
    command = _load_app_commands().get(app)
    if command is None:
        allowed = ", ".join(sorted(_load_app_commands()))
        raise ValueError(f'I do not know how to open "{app}" on this laptop yet. Allowed: {allowed}')
    await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return {"opened": True, "app": app}


async def _notification(parameters: dict[str, Any]) -> dict[str, Any]:
    title = str(parameters.get("title", "JARVIS"))
    message = str(parameters.get("message", ""))
    try:
        from winotify import Notification  # type: ignore[import-not-found]

        toast = Notification(app_id="JARVIS", title=title, msg=message)
        toast.show()
    except Exception:
        powershell = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, {json.dumps(title)}, {json.dumps(message)}, "
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 6; $n.Dispose();"
            ),
        ]
        await asyncio.create_subprocess_exec(
            *powershell,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    return {"shown": True, "title": title}


async def _system_info(parameters: dict[str, Any]) -> dict[str, Any]:
    del parameters
    result: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "windows_version": platform.platform(),
        "cpu": platform.processor(),
        "local_ip": _local_ip(),
    }
    try:
        import psutil

        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().anchor or "C:\\"))
        battery = psutil.sensors_battery()
        boot_time = psutil.boot_time()
        result.update(
            {
                "cpu_usage_percent": psutil.cpu_percent(interval=0.5),
                "ram_total_bytes": vm.total,
                "ram_used_bytes": vm.used,
                "ram_percent": vm.percent,
                "disk_total_bytes": disk.total,
                "disk_used_bytes": disk.used,
                "disk_percent": disk.percent,
                "battery_percent": battery.percent if battery else None,
                "uptime_seconds": int(time.time() - boot_time),
            }
        )
    except Exception as exc:  # noqa: BLE001 - system info remains best effort
        result["partial_error"] = str(exc)
    return result


def _local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


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
    config_file = _load_config(args)
    if args.server_url:
        os.environ["JARVIS_SERVER_URL"] = args.server_url.rstrip("/")
    device_id = args.device_id or os.environ.get("JARVIS_DEVICE_ID")
    token = args.device_token or os.environ.get("JARVIS_DEVICE_TOKEN")
    device_name = args.name or os.environ.get("JARVIS_DEVICE_NAME") or socket.gethostname()
    if not device_id or not token:
        raise SystemExit(
            "Set JARVIS_DEVICE_ID and JARVIS_DEVICE_TOKEN, or run the register command first"
        )
    url = _ws_url(_server_url(), device_id, token)
    delay = 1

    print("JARVIS Windows Agent")
    print(f"Server: {_server_url()}")
    print(f"Device: {device_name}")
    print(f"Config: {config_file}")
    print("")
    print("Capabilities:")
    for capability in CAPABILITIES:
        print(f"- {capability}")
    print("")

    while True:
        try:
            print("Connecting...")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                delay = 1
                print("Connected. Waiting for commands...")
                await ws.send(json.dumps({"type": "heartbeat", "capabilities": CAPABILITIES}))
                heartbeat = asyncio.create_task(_heartbeat(ws))
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("type") != "command":
                            continue
                        request_id = message.get("request_id")
                        message_device_id = message.get("device_id")
                        if message_device_id and message_device_id != device_id:
                            continue
                        action = message.get("action")
                        parameters = message.get("parameters") or {}
                        started = time.perf_counter()
                        try:
                            handler = HANDLERS[action]
                            result = await handler(parameters)
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "device_id": device_id,
                                "success": True,
                                "result": result,
                                "error": None,
                                "execution_time": round(time.perf_counter() - started, 3),
                            }
                        except Exception as exc:  # noqa: BLE001 - returned to server as failure
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "device_id": device_id,
                                "success": False,
                                "result": {},
                                "error": str(exc),
                                "execution_time": round(time.perf_counter() - started, 3),
                            }
                        await ws.send(json.dumps(response))
                finally:
                    heartbeat.cancel()
        except Exception as exc:  # noqa: BLE001 - reconnect loop
            print(f"Disconnected: {exc}. Reconnecting in {delay}s.", file=sys.stderr)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JARVIS Windows companion agent")
    parser.add_argument("--config", help="Path to the agent .env file")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="Register this Windows device")
    reg.add_argument("--name")
    reg.add_argument("--server-url")
    reg.add_argument("--registration-secret")
    reg.set_defaults(func=register)

    run_cmd = sub.add_parser("run", help="Connect and wait for commands")
    run_cmd.add_argument("--device-id")
    run_cmd.add_argument("--device-token")
    run_cmd.add_argument("--name")
    run_cmd.add_argument("--server-url")
    run_cmd.set_defaults(func=lambda args: asyncio.run(run(args)))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
