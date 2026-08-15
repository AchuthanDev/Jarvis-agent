"""Cross-platform tests for the Windows companion agent."""

from __future__ import annotations

import pytest

from device_agents.windows import agent


@pytest.mark.asyncio
async def test_windows_agent_rejects_forbidden_url_scheme() -> None:
    with pytest.raises(ValueError, match="only http/https"):
        await agent._open_url({"url": "file:///C:/Windows/System32/calc.exe"})


@pytest.mark.asyncio
async def test_windows_agent_rejects_unknown_application() -> None:
    with pytest.raises(ValueError, match="do not know how to open"):
        await agent._open_app({"app": "definitely-not-allowlisted"})


def test_windows_agent_writes_and_loads_env(tmp_path, monkeypatch) -> None:
    config = tmp_path / ".env"
    monkeypatch.delenv("JARVIS_DEVICE_TOKEN", raising=False)

    agent._write_env_file(
        config,
        {
            "JARVIS_SERVER_URL": "http://jarvis.local:8000",
            "JARVIS_DEVICE_ID": "device-id",
            "JARVIS_DEVICE_TOKEN": "secret-token",
            "JARVIS_DEVICE_NAME": "Laptop",
        },
    )
    agent._load_env_file(config)

    assert "secret-token" in config.read_text(encoding="utf-8")
    assert agent.os.environ["JARVIS_DEVICE_TOKEN"] == "secret-token"
