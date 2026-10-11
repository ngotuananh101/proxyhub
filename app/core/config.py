from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database connection, assembled into a SQLAlchemy URL by build_db_url().
    DB_CONNECTION: str = "sqlite"  # "sqlite" | "postgresql" (alias "postgres")
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    # For sqlite this is the file path; for postgres the database name.
    DB_DATABASE: str = "./proxyhub.db"
    DB_USERNAME: str = "proxyhub"
    DB_PASSWORD: str = ""
    DB_SSLMODE: str = ""  # e.g. "require"; omitted from the URL when empty

    APP_KEY: str = "change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_TTL: int = 1440
    INTERNAL_API_KEY: str = "change_me"
    CORS_ORIGINS: str = "http://localhost:5173"
    QUEUE_BROKER_URL: str = "redis://127.0.0.1:6379/1"
    QUEUE_RESULT_BACKEND: str = "redis://127.0.0.1:6379/2"
    HEALTH_CHECK_URL: str = "https://api.ipify.org"
    HEALTH_CHECK_TIMEOUT: float = 6.0
    HEALTH_CHECK_INTERVAL: float = 300.0
    HEALTH_CHECK_CONCURRENCY: int = 50
    REQUEST_LOG_RETENTION_DAYS: int = 30
    GATEWAY_AUTH_CACHE_TTL: float = 60.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()


def build_db_url(s: Settings) -> str:
    """Assemble a SQLAlchemy database URL from the discrete DB_* settings.

    SQLite uses DB_DATABASE as the file path and ignores host/port/credentials.
    PostgreSQL (also accepts the "postgres" alias) builds a psycopg URL, URL-
    encoding the credentials so special characters cannot break the URL, and
    appends ``?sslmode=`` when DB_SSLMODE is set.
    """
    connection = s.DB_CONNECTION.lower()
    if connection == "sqlite":
        return f"sqlite:///{s.DB_DATABASE}"
    if connection in ("postgresql", "postgres"):
        user = quote_plus(s.DB_USERNAME)
        password = quote_plus(s.DB_PASSWORD)
        url = (
            f"postgresql+psycopg://{user}:{password}"
            f"@{s.DB_HOST}:{s.DB_PORT}/{s.DB_DATABASE}"
        )
        if s.DB_SSLMODE:
            url = f"{url}?sslmode={s.DB_SSLMODE}"
        return url
    raise ValueError(f"Unsupported DB_CONNECTION: {s.DB_CONNECTION!r}")


# Placeholder values that must never reach a running deployment.
INSECURE_PLACEHOLDERS = {"", "change_me"}


def validate_secrets(s: Settings) -> None:
    """Fail fast if auth secrets are still placeholder values.

    Called at server/worker startup so a deployment that forgot to set
    APP_KEY or INTERNAL_API_KEY cannot silently run with values
    anyone can guess.
    """
    unset = [
        name
        for name in ("APP_KEY", "INTERNAL_API_KEY")
        if getattr(s, name) in INSECURE_PLACEHOLDERS
    ]
    if unset:
        raise RuntimeError(
            "Refusing to start with insecure default secrets: "
            + ", ".join(unset)
            + ". Set real values in .env (see .env.example)."
        )
