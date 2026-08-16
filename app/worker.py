import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery
from sqlmodel import Session, col, select

from app.core import database
from app.core.config import settings
from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting
from app.services import health_service
from app.services.settings_service import get_all as get_settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "proxyhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Fixed 60s tick: the task itself gates on HEALTH_CHECK_INTERVAL (stored in
# the DB), so interval changes made from the dashboard take effect within a
# minute without restarting beat.
celery_app.conf.beat_schedule = {
    "check-all-proxies": {
        "task": "app.worker.check_all_proxies",
        "schedule": 60.0,
    }
}

CHECKABLE_SCHEMES = ("http", "https")
CHECKABLE_STATUSES = (ProxyStatus.ALIVE, ProxyStatus.UNKNOWN)
LAST_RUN_KEY = "HEALTH_CHECK_LAST_RUN_AT"


def _get_engine():
    """Indirection so tests can swap in an in-memory DB engine."""
    return database.engine


def _seconds_since_last_run(session: Session) -> float | None:
    row = session.exec(select(AppSetting).where(AppSetting.key == LAST_RUN_KEY)).first()
    if row is None:
        return None
    try:
        last_run = datetime.fromisoformat(row.value)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - last_run).total_seconds()


def _mark_last_run(session: Session) -> None:
    row = session.exec(select(AppSetting).where(AppSetting.key == LAST_RUN_KEY)).first()
    if row is None:
        row = AppSetting(key=LAST_RUN_KEY, value="")
    row.value = datetime.now(timezone.utc).isoformat()
    session.add(row)
    session.commit()


async def _check_all(
    proxies: list[Proxy], url: str, timeout: float, concurrency: int
) -> list[health_service.CheckResult]:
    """Check all proxies concurrently, bounded by `concurrency`."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(proxy: Proxy) -> health_service.CheckResult:
        async with semaphore:
            return await health_service.check_proxy(proxy, url, timeout)

    return list(await asyncio.gather(*(_bounded(p) for p in proxies)))


@celery_app.task(name="app.worker.check_all_proxies")
def check_all_proxies(force: bool = False) -> int:
    """Health-check all http/https proxies in a single task.

    Beat fires every 60s; the task skips unless HEALTH_CHECK_INTERVAL has
    elapsed since the last run, so the interval is editable at runtime.
    """
    with Session(_get_engine()) as session:
        values = get_settings(session)
        interval = float(values["HEALTH_CHECK_INTERVAL"])
        if not force:
            elapsed = _seconds_since_last_run(session)
            if elapsed is not None and elapsed < interval:
                logger.debug("Skipping: %.0fs since last run, interval is %.0fs", elapsed, interval)
                return 0

        proxies = session.exec(
            select(Proxy).where(
                col(Proxy.scheme).in_(CHECKABLE_SCHEMES),
                col(Proxy.status).in_(CHECKABLE_STATUSES),
            )
        ).all()
        if not proxies:
            logger.info("No checkable proxies found")
            _mark_last_run(session)
            return 0

        results = asyncio.run(
            _check_all(
                proxies,
                url=str(values["HEALTH_CHECK_URL"]),
                timeout=float(values["HEALTH_CHECK_TIMEOUT"]),
                concurrency=int(values["HEALTH_CHECK_CONCURRENCY"]),
            )
        )

        now = datetime.now(timezone.utc)
        for proxy, result in zip(proxies, results):
            proxy.status = ProxyStatus.ALIVE if result.alive else ProxyStatus.DEAD
            proxy.latency_ms = result.latency_ms
            proxy.last_checked_at = now
            proxy.updated_at = now
            session.add(proxy)
        _mark_last_run(session)
        session.commit()

    alive = sum(1 for r in results if r.alive)
    logger.info("Checked %d proxies: %d alive, %d dead", len(results), alive, len(results) - alive)
    return len(results)
