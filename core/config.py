"""Application configuration.

Settings are loaded from environment variables (and an optional `.env` file)
by pydantic-settings. Field names map to env vars case-insensitively,
e.g. ``database_url`` <-> ``DATABASE_URL``.

Never put secrets in this file. Use the environment / `.env` (gitignored).
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "JARVIS"
    environment: str = "dev"
    debug: bool = False
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Directory served at ``/`` by the API (dashboard UI).
    static_dir: Path = Path("apps/dashboard/static")

    # Comma-separated list of allowed CORS origins.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "postgresql+asyncpg://jarvis:jarvis@localhost:5432/jarvis"
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    jarvis_secret_key: str = Field(default="change-me", repr=False)

    # LLM provider abstraction (Phase 2+).
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_base_url: str = ""
    llm_temperature: float = 0.7
    llm_max_tokens: int | None = None

    # Tool calling (Phase 3). Set to false to disable tools entirely.
    tools_enabled: bool = True
    # Highest tool risk the LLM may execute without explicit permission.
    tool_max_autonomous_risk: int = 1

    # Device companion registration/auth (Phase 4).
    device_registration_secret: str = Field(default="", repr=False)
    device_command_timeout_seconds: float = 20.0

    # Home Assistant integration (Phase 8+). Server-side only.
    home_assistant_url: str = ""
    home_assistant_token: str = Field(default="", repr=False)

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
