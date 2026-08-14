from core.config import Settings


def test_defaults_without_env() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "JARVIS"
    assert settings.environment == "dev"
    assert settings.log_level == "INFO"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.llm_provider == "openai"
    assert settings.jarvis_secret_key


def test_env_override() -> None:
    settings = Settings(_env_file=None, api_port=9090, log_level="DEBUG")
    assert settings.api_port == 9090
    assert settings.log_level == "DEBUG"


def test_cors_origin_list() -> None:
    settings = Settings(_env_file=None, cors_origins="http://a:1, http://b:2, ")
    assert settings.cors_origin_list() == ["http://a:1", "http://b:2"]
