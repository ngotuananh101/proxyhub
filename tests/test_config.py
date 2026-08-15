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
