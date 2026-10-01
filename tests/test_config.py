# tests/test_config.py
import pytest

from app.core.config import Settings, validate_secrets


def test_settings_defaults():
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_ACCESS_TOKEN_TTL == 1440
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_settings_cors_parsing():
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
        CORS_ORIGINS="http://a.com,http://b.com",
    )
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_settings_ignores_extra_env_vars(monkeypatch):
    # Values that live only in .env.example / docker-compose must not break
    # startup when Settings does not declare them.
    monkeypatch.setenv("QUEUE_BROKER_URL", "redis://127.0.0.1:6379/1")
    monkeypatch.setenv("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.DB_URL == "sqlite:///./test.db"


def test_queue_and_health_check_defaults(monkeypatch):
    for key in (
        "QUEUE_BROKER_URL",
        "QUEUE_RESULT_BACKEND",
        "HEALTH_CHECK_URL",
        "HEALTH_CHECK_TIMEOUT",
        "HEALTH_CHECK_INTERVAL",
        "HEALTH_CHECK_CONCURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.QUEUE_BROKER_URL == "redis://127.0.0.1:6379/1"
    assert s.QUEUE_RESULT_BACKEND == "redis://127.0.0.1:6379/2"
    assert s.HEALTH_CHECK_URL == "https://api.ipify.org"
    assert s.HEALTH_CHECK_TIMEOUT == 6.0
    assert s.HEALTH_CHECK_INTERVAL == 300.0
    assert s.HEALTH_CHECK_CONCURRENCY == 50


def test_validate_secrets_accepts_real_values():
    s = Settings(
        _env_file=None,
        APP_KEY="a-real-random-secret",
        INTERNAL_API_KEY="a-real-internal-key",
    )
    validate_secrets(s)  # must not raise


@pytest.mark.parametrize("bad", ["change_me", ""])
def test_validate_secrets_rejects_placeholders(bad):
    s = Settings(
        _env_file=None,
        APP_KEY=bad,
        INTERNAL_API_KEY=bad,
    )
    with pytest.raises(RuntimeError, match="APP_KEY, INTERNAL_API_KEY"):
        validate_secrets(s)


def test_validate_secrets_names_only_unset_keys():
    s = Settings(
        _env_file=None,
        APP_KEY="a-real-random-secret",
        INTERNAL_API_KEY="change_me",
    )
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY") as exc_info:
        validate_secrets(s)
    assert "APP_KEY" not in str(exc_info.value)
