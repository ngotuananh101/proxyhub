"""Registry of settings editable from the dashboard.

Each entry defines the type, bounds, and env-derived default for one key
stored in the `appsettings` table. Adding a new editable setting only
requires a new entry here — the API, validation, and the Settings page
pick it up automatically. Infra/security values (DATABASE_URL, SECRET_KEY,
CELERY_*, INTERNAL_API_KEY, CORS_ORIGINS) are intentionally excluded:
they require a restart and must stay in .env.
"""

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    description: str
    type: str  # "string" | "int" | "float"
    default: str | int | float
    min: float | None = None
    max: float | None = None


REGISTRY: dict[str, SettingDef] = {
    d.key: d
    for d in [
        SettingDef(
            key="HEALTH_CHECK_URL",
            label="Health check URL",
            description="Target URL fetched through each proxy to verify it works.",
            type="string",
            default=settings.HEALTH_CHECK_URL,
        ),
        SettingDef(
            key="HEALTH_CHECK_TIMEOUT",
            label="Health check timeout (seconds)",
            description="Maximum time allowed per proxy check before it is marked dead.",
            type="float",
            default=settings.HEALTH_CHECK_TIMEOUT,
            min=1,
            max=60,
        ),
        SettingDef(
            key="HEALTH_CHECK_INTERVAL",
            label="Health check interval (seconds)",
            description="How often the automatic health check cycle runs.",
            type="float",
            default=settings.HEALTH_CHECK_INTERVAL,
            min=60,
            max=86400,
        ),
        SettingDef(
            key="HEALTH_CHECK_CONCURRENCY",
            label="Health check concurrency",
            description="Number of proxies checked at the same time.",
            type="int",
            default=settings.HEALTH_CHECK_CONCURRENCY,
            min=1,
            max=500,
        ),
        SettingDef(
            key="SOURCE_FETCH_TIMEOUT",
            label="Source fetch timeout (seconds)",
            description="Maximum time allowed when downloading a proxy source file.",
            type="float",
            default=30.0,
            min=5,
            max=120,
        ),
        SettingDef(
            key="DEAD_PROXY_RETENTION_DAYS",
            label="Dead proxy retention (days)",
            description=(
                "Proxies dead for longer than this are removed automatically "
                "when a source is fetched. 0 disables removal."
            ),
            type="float",
            default=7.0,
            min=0,
            max=365,
        ),
        SettingDef(
            key="TIMEZONE",
            label="Timezone",
            description=(
                "IANA timezone used to display dates and times in the "
                "dashboard, e.g. UTC or Asia/Ho_Chi_Minh."
            ),
            type="string",
            default="UTC",
        ),
    ]
}
