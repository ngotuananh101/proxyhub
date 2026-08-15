import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery
from sqlmodel import Session, col, select

from app.core import database
from app.core.config import settings
from app.models.proxy import Proxy, ProxyStatus
from app.services import health_service

logger = logging.getLogger(__name__)

celery_app = Celery(
    "proxyhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.beat_schedule = {
    "check-all-proxies": {
        "task": "app.worker.check_all_proxies",
        "schedule": settings.HEALTH_CHECK_INTERVAL,
    }
}

CHECKABLE_SCHEMES = ("http", "https")


def _get_engine():
    """Indirection để test có thể thay engine bằng DB in-memory."""
    return database.engine


async def _check_all(proxies: list[Proxy]) -> list[health_service.CheckResult]:
    """Check song song toàn bộ proxy, giới hạn bởi HEALTH_CHECK_CONCURRENCY."""
    semaphore = asyncio.Semaphore(settings.HEALTH_CHECK_CONCURRENCY)

    async def _bounded(proxy: Proxy) -> health_service.CheckResult:
        async with semaphore:
            return await health_service.check_proxy(proxy)

    return list(await asyncio.gather(*(_bounded(p) for p in proxies)))


@celery_app.task(name="app.worker.check_all_proxies")
def check_all_proxies() -> int:
    """Kiểm tra sức khoẻ toàn bộ proxy http/https trong một task duy nhất."""
    with Session(_get_engine()) as session:
        proxies = session.exec(
            select(Proxy).where(col(Proxy.scheme).in_(CHECKABLE_SCHEMES))
        ).all()
        if not proxies:
            logger.info("No checkable proxies found")
            return 0

        results = asyncio.run(_check_all(proxies))

        now = datetime.now(timezone.utc)
        for proxy, result in zip(proxies, results):
            proxy.status = ProxyStatus.ALIVE if result.alive else ProxyStatus.DEAD
            proxy.latency_ms = result.latency_ms
            proxy.last_checked_at = now
            proxy.updated_at = now
            session.add(proxy)
        session.commit()

    alive = sum(1 for r in results if r.alive)
    logger.info("Checked %d proxies: %d alive, %d dead", len(results), alive, len(results) - alive)
    return len(results)
