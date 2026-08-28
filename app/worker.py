import asyncio
import logging
import time
from datetime import datetime, timezone

from celery import Celery
from redis import Redis
from redis.exceptions import LockError
from sqlmodel import Session, col, select

from app.core import database
from app.core.config import settings, validate_secrets
from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting
from app.models.source import ProxySource
from app.services import health_service
from app.services.events import broadcast_sync
from app.services.log_service import purge_old_request_logs
from app.services.settings_service import get_all as get_settings
from app.services.source_service import fetch_and_import, is_due, seed_default_sources

logger = logging.getLogger(__name__)

# Celery workers/beat never run the FastAPI lifespan, so validate here too.
validate_secrets(settings)

celery_app = Celery(
    "proxyhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Fixed 60s tick: the tasks themselves gate on intervals stored in the DB
# (HEALTH_CHECK_INTERVAL, per-source interval_minutes), so changes made from
# the dashboard take effect within a minute without restarting beat.
celery_app.conf.beat_schedule = {
    "check-all-proxies": {
        "task": "app.worker.check_all_proxies",
        "schedule": 60.0,
    },
    "fetch-proxy-sources": {
        "task": "app.worker.fetch_due_sources",
        "schedule": 60.0,
    },
    "purge-request-logs": {
        "task": "app.worker.purge_request_logs",
        "schedule": 3600.0,
    },
}

CHECKABLE_SCHEMES = ("http", "https")
CHECKABLE_STATUSES = (ProxyStatus.ALIVE, ProxyStatus.UNKNOWN)
LAST_RUN_KEY = "HEALTH_CHECK_LAST_RUN_AT"
# How often finished checks are flushed to the DB (and stats broadcast) while
# a cycle is running, so the dashboard updates progressively.
FLUSH_INTERVAL = 2.0


def _get_engine():
    """Indirection so tests can swap in an in-memory DB engine."""
    return database.engine


# Beat ticks every 60s but a cycle can run for minutes, and "Check now" can
# fire mid-cycle. A Redis lock makes overlapping dispatches skip instead of
# doubling the load on the proxy pool. The TTL releases the lock if a worker
# dies mid-run.
CHECK_LOCK_NAME = "proxyhub:check_all_proxies"
FETCH_LOCK_NAME = "proxyhub:fetch_due_sources"
PURGE_LOG_LOCK_NAME = "proxyhub:purge_request_logs"
LOCK_TIMEOUT = 900.0


def _get_lock_client() -> Redis:
    """Indirection so tests can swap in a fake Redis client."""
    return Redis.from_url(settings.CELERY_BROKER_URL)


def _acquire_lock(name: str):
    """Try to take a named lock without waiting. Returns None if held."""
    lock = _get_lock_client().lock(name, timeout=LOCK_TIMEOUT)
    try:
        if lock.acquire(blocking=False):
            return lock
    except LockError as e:
        logger.warning("Could not acquire lock %s: %s", name, e)
    return None


def _release_lock(lock) -> None:
    try:
        lock.release()
    except LockError:
        # TTL already expired or the lock was lost; nothing to clean up.
        pass


def _broadcast_stats(session: Session) -> None:
    """Push fresh summary counts to connected dashboard clients."""
    from sqlmodel import func

    stats = {
        "total": session.exec(select(func.count(Proxy.id))).one(),
        "alive": session.exec(
            select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.ALIVE)
        ).one(),
        "dead": session.exec(
            select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.DEAD)
        ).one(),
        "unknown": session.exec(
            select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.UNKNOWN)
        ).one(),
    }
    broadcast_sync("stats", stats)


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
    proxies: list[Proxy],
    url: str,
    timeout: float,
    concurrency: int,
    on_result,
) -> list[health_service.CheckResult]:
    """Check all proxies concurrently, bounded by `concurrency`.

    `on_result(proxy, result)` fires as soon as each check finishes, so the
    caller can persist and broadcast results progressively.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(proxy: Proxy) -> health_service.CheckResult:
        async with semaphore:
            result = await health_service.check_proxy(proxy, url, timeout)
        on_result(proxy, result)
        return result

    return list(await asyncio.gather(*(_bounded(p) for p in proxies)))


def _apply_result(session: Session, proxy: Proxy, result: health_service.CheckResult) -> None:
    """Write one finished check result onto the session (not yet committed)."""
    now = datetime.now(timezone.utc)
    proxy.status = ProxyStatus.ALIVE if result.alive else ProxyStatus.DEAD
    proxy.latency_ms = result.latency_ms
    proxy.last_checked_at = now
    proxy.updated_at = now
    session.add(proxy)


@celery_app.task(name="app.worker.check_all_proxies")
def check_all_proxies(force: bool = False) -> int:
    """Health-check all http/https proxies in a single task.

    Beat fires every 60s; the task skips unless HEALTH_CHECK_INTERVAL has
    elapsed since the last run, so the interval is editable at runtime.
    Results are flushed to the DB (and stats broadcast) every FLUSH_INTERVAL
    seconds while the cycle runs, so the dashboard updates progressively.
    """
    lock = _acquire_lock(CHECK_LOCK_NAME)
    if lock is None:
        logger.info("A health check cycle is already running; skipping")
        return 0
    try:
        with Session(_get_engine()) as session:
            values = get_settings(session)
            interval = float(values["HEALTH_CHECK_INTERVAL"])
            if not force:
                elapsed = _seconds_since_last_run(session)
                if elapsed is not None and elapsed < interval:
                    logger.debug(
                        "Skipping: %.0fs since last run, interval is %.0fs", elapsed, interval
                    )
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
                _broadcast_stats(session)
                return 0

            # Periodic flush: commit finished results and push fresh stats so
            # the dashboard tracks the cycle live instead of waiting for it.
            last_flush = time.monotonic()

            def on_result(proxy: Proxy, result: health_service.CheckResult) -> None:
                nonlocal last_flush
                _apply_result(session, proxy, result)
                if time.monotonic() - last_flush >= FLUSH_INTERVAL:
                    session.commit()
                    _broadcast_stats(session)
                    last_flush = time.monotonic()

            results = asyncio.run(
                _check_all(
                    proxies,
                    url=str(values["HEALTH_CHECK_URL"]),
                    timeout=float(values["HEALTH_CHECK_TIMEOUT"]),
                    concurrency=int(values["HEALTH_CHECK_CONCURRENCY"]),
                    on_result=on_result,
                )
            )

            # Final flush: results finished after the last periodic flush
            session.commit()
            _mark_last_run(session)
            _broadcast_stats(session)

        alive = sum(1 for r in results if r.alive)
        logger.info(
            "Checked %d proxies: %d alive, %d dead", len(results), alive, len(results) - alive
        )
        return len(results)
    finally:
        _release_lock(lock)


@celery_app.task(name="app.worker.fetch_due_sources")
def fetch_due_sources() -> int:
    """Fetch every enabled source whose interval has elapsed.

    Beat fires every 60s; each source is gated on its own interval_minutes,
    so intervals are editable at runtime.
    """
    lock = _acquire_lock(FETCH_LOCK_NAME)
    if lock is None:
        logger.info("A source fetch cycle is already running; skipping")
        return 0
    try:
        fetched = 0
        with Session(_get_engine()) as session:
            from app.services.tenant_service import ensure_default_tenant
            default_tenant = ensure_default_tenant(session)
            seed_default_sources(session, tenant_id=default_tenant.id)
            values = get_settings(session)
            timeout = float(values["SOURCE_FETCH_TIMEOUT"])
            retention_days = float(values["DEAD_PROXY_RETENTION_DAYS"])
            now = datetime.now(timezone.utc)
            sources = session.exec(select(ProxySource)).all()
            for source in sources:
                if not is_due(source, now):
                    continue
                fetch_and_import(
                    session, source, timeout=timeout, retention_days=retention_days, tenant_id=source.tenant_id
                )
                fetched += 1

        if fetched:
            logger.info("Fetched %d proxy sources", fetched)
        return fetched
    finally:
        _release_lock(lock)


@celery_app.task(name="purge-request-logs")
def purge_request_logs() -> int:
    """Delete request logs older than the configured retention period.

    Beat fires hourly; the retention is read from the DB setting so changes
    made from the dashboard take effect without restarting beat.
    """
    lock = _acquire_lock(PURGE_LOG_LOCK_NAME)
    if lock is None:
        logger.info("A request-log purge is already running; skipping")
        return 0
    try:
        with Session(_get_engine()) as session:
            values = get_settings(session)
            retention_days = int(values["REQUEST_LOG_RETENTION_DAYS"])
            removed = purge_old_request_logs(session, retention_days)
        if removed:
            logger.info("Purged %d old request logs", removed)
        return removed
    finally:
        _release_lock(lock)
