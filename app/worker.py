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
    "check-all-proxies-every-5-min": {
        "task": "app.worker.check_all_proxies",
        "schedule": 300.0,
    }
}

CHECKABLE_SCHEMES = ("http", "https")


def _get_engine():
    """Indirection để test có thể thay engine bằng DB in-memory."""
    return database.engine


@celery_app.task(name="app.worker.check_all_proxies")
def check_all_proxies() -> int:
    with Session(_get_engine()) as session:
        proxies = session.exec(
            select(Proxy).where(col(Proxy.scheme).in_(CHECKABLE_SCHEMES))
        ).all()
        proxy_ids = [p.id for p in proxies]
    for proxy_id in proxy_ids:
        check_proxy_task.delay(proxy_id)
    logger.info("Dispatched %d health check tasks", len(proxy_ids))
    return len(proxy_ids)


@celery_app.task(name="app.worker.check_proxy_task")
def check_proxy_task(proxy_id: int) -> str:
    with Session(_get_engine()) as session:
        proxy = session.get(Proxy, proxy_id)
        if proxy is None:
            logger.warning("Proxy %s not found, skipping", proxy_id)
            return "not_found"

        result = health_service.check_proxy(proxy)
        proxy.status = ProxyStatus.ALIVE if result.alive else ProxyStatus.DEAD
        proxy.latency_ms = result.latency_ms
        proxy.last_checked_at = datetime.now(timezone.utc)
        proxy.updated_at = datetime.now(timezone.utc)
        session.add(proxy)
        session.commit()
        return "alive" if result.alive else "dead"
