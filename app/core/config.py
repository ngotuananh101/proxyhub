from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_URL: str = "sqlite:///./proxyhub.db"
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

# Placeholder values that must never reach a running deployment. Any value
# starting with this prefix counts as unset, so the secrets shipped in
# .env.example ("change_me_to_a_random_secure_secret_key") are caught too,
# not just the bare "change_me" fallback baked into Settings.
INSECURE_PLACEHOLDER_PREFIX = "change_me"


def _is_insecure(value: str) -> bool:
    return not value or value.strip().startswith(INSECURE_PLACEHOLDER_PREFIX)


def validate_secrets(s: Settings) -> None:
    """Fail fast if auth secrets are still placeholder values.

    Called at server/worker startup so a deployment that forgot to set
    APP_KEY or INTERNAL_API_KEY cannot silently run with values
    anyone can guess.
    """
    unset = [
        name
        for name in ("APP_KEY", "INTERNAL_API_KEY")
        if _is_insecure(getattr(s, name))
    ]
    if unset:
        raise RuntimeError(
            "Refusing to start with insecure default secrets: "
            + ", ".join(unset)
            + ". Set real values in .env (see .env.example)."
        )
