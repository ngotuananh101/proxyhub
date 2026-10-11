# tests/test_config.py
import pytest

from app.core.config import Settings, build_db_url, build_redis_url, validate_secrets


def test_settings_defaults():
    s = Settings(
        _env_file=None,
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_ACCESS_TOKEN_TTL == 1440
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_settings_cors_parsing():
    s = Settings(
        _env_file=None,
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
        CORS_ORIGINS="http://a.com,http://b.com",
    )
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_settings_ignores_extra_env_vars(monkeypatch):
    # Values that live only in .env.example / docker-compose must not break
    # startup when Settings does not declare them. A legacy DB_URL is one of
    # them now that the URL is assembled from discrete DB_* variables.
    monkeypatch.setenv("QUEUE_BROKER_URL", "redis://127.0.0.1:6379/1")
    monkeypatch.setenv("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
    monkeypatch.setenv("DB_URL", "postgresql+psycopg://ignored@host/db")
    monkeypatch.delenv("DB_CONNECTION", raising=False)
    monkeypatch.delenv("DB_DATABASE", raising=False)
    s = Settings(
        _env_file=None,
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.DB_CONNECTION == "sqlite"
    assert build_db_url(s) == "sqlite:///./proxyhub.db"


def test_build_db_url_sqlite():
    s = Settings(
        _env_file=None,
        DB_CONNECTION="sqlite",
        DB_DATABASE="./proxyhub.db",
    )
    assert build_db_url(s) == "sqlite:///./proxyhub.db"


def test_build_db_url_postgres():
    s = Settings(
        _env_file=None,
        DB_CONNECTION="postgresql",
        DB_HOST="db.internal",
        DB_PORT=5432,
        DB_DATABASE="proxyhub",
        DB_USERNAME="proxyhub",
        DB_PASSWORD="secret",
    )
    assert (
        build_db_url(s)
        == "postgresql+psycopg://proxyhub:secret@db.internal:5432/proxyhub"
    )


def test_build_db_url_postgres_accepts_postgres_alias():
    s = Settings(
        _env_file=None,
        DB_CONNECTION="postgres",
        DB_HOST="127.0.0.1",
        DB_PORT=5433,
        DB_DATABASE="proxyhub",
        DB_USERNAME="u",
        DB_PASSWORD="p",
    )
    assert build_db_url(s) == "postgresql+psycopg://u:p@127.0.0.1:5433/proxyhub"


def test_build_db_url_quotes_special_chars_in_password():
    s = Settings(
        _env_file=None,
        DB_CONNECTION="postgresql",
        DB_HOST="host",
        DB_PORT=5432,
        DB_DATABASE="proxyhub",
        DB_USERNAME="user@example.com",
        DB_PASSWORD="p@ss:w/rd?",
    )
    assert (
        build_db_url(s)
        == "postgresql+psycopg://user%40example.com:p%40ss%3Aw%2Frd%3F@host:5432/proxyhub"
    )


def test_build_db_url_appends_sslmode():
    s = Settings(
        _env_file=None,
        DB_CONNECTION="postgresql",
        DB_HOST="aiven.example.com",
        DB_PORT=13600,
        DB_DATABASE="proxyhub",
        DB_USERNAME="avnadmin",
        DB_PASSWORD="pw",
        DB_SSLMODE="require",
    )
    assert (
        build_db_url(s)
        == "postgresql+psycopg://avnadmin:pw@aiven.example.com:13600/proxyhub?sslmode=require"
    )


def test_build_db_url_rejects_unknown_connection():
    s = Settings(_env_file=None, DB_CONNECTION="mysql")
    with pytest.raises(ValueError, match="mysql"):
        build_db_url(s)


# --- build_redis_url: rediss:// needs ssl_cert_reqs for the Celery backend ---


def test_build_redis_url_leaves_plain_redis_untouched():
    assert (
        build_redis_url("redis://127.0.0.1:6379/1")
        == "redis://127.0.0.1:6379/1"
    )


def test_build_redis_url_adds_ssl_cert_reqs_to_rediss():
    assert (
        build_redis_url("rediss://default:pw@host:13601/1")
        == "rediss://default:pw@host:13601/1?ssl_cert_reqs=required"
    )


def test_build_redis_url_keeps_existing_ssl_cert_reqs():
    url = "rediss://default:pw@host:13601/1?ssl_cert_reqs=none"
    assert build_redis_url(url) == url


def test_build_redis_url_preserves_other_query_params():
    assert (
        build_redis_url("rediss://h:13601/1?ssl_check_hostname=false")
        == "rediss://h:13601/1?ssl_check_hostname=false&ssl_cert_reqs=required"
    )


def test_build_redis_url_defaults_ssl_cert_reqs_for_backend(monkeypatch):
    monkeypatch.delenv("QUEUE_BROKER_URL", raising=False)
    monkeypatch.delenv("QUEUE_RESULT_BACKEND", raising=False)
    s = Settings(
        _env_file=None,
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
        QUEUE_BROKER_URL="rediss://default:pw@host:13601/1",
        QUEUE_RESULT_BACKEND="rediss://default:pw@host:13601/2",
    )
    assert s.redis_broker_url.endswith("?ssl_cert_reqs=required")
    assert s.redis_result_backend.endswith("?ssl_cert_reqs=required")
    # Plain redis must not be rewritten.
    plain = Settings(
        _env_file=None,
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
        QUEUE_BROKER_URL="redis://127.0.0.1:6379/1",
    )
    assert plain.redis_broker_url == "redis://127.0.0.1:6379/1"


def test_celery_backend_accepts_normalized_rediss_url(monkeypatch):
    # Regression: a bare rediss:// URL makes the Celery redis *backend* raise
    # "A rediss:// URL must have parameter ssl_cert_reqs". The normalized URL
    # must construct a backend without error.
    from celery import Celery

    url = build_redis_url("rediss://default:pw@host:13601/2")
    app = Celery("probe", broker=url, backend=url)
    assert app.backend is not None  # must not raise


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
