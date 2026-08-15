# tests/test_config.py
from app.core.config import Settings


def test_settings_defaults():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 1440
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_settings_cors_parsing():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="abc",
        INTERNAL_API_KEY="key",
        CORS_ORIGINS="http://a.com,http://b.com",
    )
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_settings_ignores_extra_env_vars(monkeypatch):
    # .env.example ships Part-2 vars (Redis/Celery) the MVP Settings doesn't
    # declare; they must not break startup.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.DATABASE_URL == "sqlite:///./test.db"


def test_celery_and_health_check_defaults(monkeypatch):
    for key in (
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "HEALTH_CHECK_URL",
        "HEALTH_CHECK_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.CELERY_BROKER_URL == "redis://localhost:6379/1"
    assert s.CELERY_RESULT_BACKEND == "redis://localhost:6379/2"
    assert s.HEALTH_CHECK_URL == "https://api.ipify.org"
    assert s.HEALTH_CHECK_TIMEOUT == 10.0

