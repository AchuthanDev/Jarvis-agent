"""``server.system_status`` — host resource usage (psutil)."""

from __future__ import annotations

import platform
import socket
import time
from datetime import datetime, timezone

from core.tools.base import RISK_READ_ONLY, Tool, ToolContext


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


async def _system_status(*, context: ToolContext) -> dict:
    del context  # unused
    import psutil

    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    return {
        "hostname": _hostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "server_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "booted_at": boot_time.isoformat(timespec="seconds"),
        "cpu_percent": round(cpu, 1),
        "memory_percent": round(mem.percent, 1),
        "memory_total_bytes": mem.total,
        "memory_available_bytes": mem.available,
        "disk_percent": round(disk.percent, 1),
        "disk_free_bytes": disk.free,
    }


def system_status_tool() -> Tool:
    return Tool(
        name="server.system_status",
        description=(
            "Resource usage and uptime of the JARVIS server (CPU, memory, disk, uptime). "
            "Use to answer questions about the server's health or performance."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        fn=_system_status,
        risk=RISK_READ_ONLY,
        timeout=10.0,
    )
