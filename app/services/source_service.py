import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import tuple_
from sqlmodel import Session, col, select

from app.models.proxy import Proxy, ProxyStatus
from app.models.source import ProxySource
from app.services.proxy_service import parse_proxy_line

logger = logging.getLogger(__name__)

MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2MB


def normalize_line(line: str) -> str | None:
    """Normalize one source line into a parseable proxy URL.

    Accepts `ip:port` (defaults to http) and full scheme:// URLs;
    blank lines and comments are dropped.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "://" not in line:
        line = f"http://{line}"
    return line


def import_source_text(session: Session, text: str) -> tuple[int, int]:
    """Import proxies from fetched text. Returns (imported, duplicates).

    Existing proxies are looked up with a single bulk query instead of one
    SELECT per line: thousands of round-trips would keep the write
    transaction open long enough to starve the API's busy_timeout.
    """
    parsed: list[dict] = []
    seen: set[tuple[str, str, int]] = set()

    for raw in text.splitlines():
        line = normalize_line(raw)
        if line is None:
            continue
        item = parse_proxy_line(line)
        if item is None:
            continue
        key = (item["scheme"], item["host"], item["port"])
        if key in seen:
            continue
        seen.add(key)
        parsed.append(item)

    if not parsed:
        session.commit()
        return 0, 0

    keys = [(item["scheme"], item["host"], item["port"]) for item in parsed]
    existing_proxies = session.exec(
        select(Proxy).where(
            tuple_(Proxy.scheme, Proxy.host, Proxy.port).in_(keys)
        )
    ).all()
    existing_map = {(p.scheme, p.host, p.port): p for p in existing_proxies}

    imported = 0
    duplicates = 0
    now = datetime.now(timezone.utc)
    for item in parsed:
        key = (item["scheme"], item["host"], item["port"])
        if key in existing_map:
            duplicates += 1
            proxy = existing_map[key]
            if proxy.status == ProxyStatus.DEAD:
                proxy.status = ProxyStatus.UNKNOWN
                proxy.updated_at = now
                session.add(proxy)
            continue
        session.add(Proxy(**item))
        imported += 1

    session.commit()
    return imported, duplicates


def purge_old_dead_proxies(session: Session, retention_days: float) -> int:
    """Delete proxies dead for longer than the retention period."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    dead = session.exec(
        select(Proxy).where(
            Proxy.status == ProxyStatus.DEAD,
            col(Proxy.updated_at) < cutoff,
        )
    ).all()
    for proxy in dead:
        session.delete(proxy)
    session.commit()
    return len(dead)


async def _download(url: str, timeout: float) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    if len(resp.content) > MAX_CONTENT_BYTES:
        raise ValueError(f"Response too large ({len(resp.content)} bytes)")
    return resp.content.decode("utf-8", errors="replace")


def is_due(source: ProxySource, now: datetime) -> bool:
    if not source.enabled:
        return False
    if source.last_fetched_at is None:
        return True
    last = source.last_fetched_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() >= source.interval_minutes * 60


def fetch_and_import(
    session: Session, source: ProxySource, timeout: float, retention_days: float
) -> str:
    """Fetch one source, import its proxies, record the outcome.

    Returns the status string stored on the source.
    """
    try:
        text = asyncio.run(_download(source.url, timeout))
        imported, duplicates = import_source_text(session, text)
        purged = purge_old_dead_proxies(session, retention_days)
        status = f"ok: {imported} imported, {duplicates} duplicates"
        if purged:
            status += f", {purged} old dead removed"
    except Exception as e:
        logger.warning("Source %s failed: %s", source.name, e)
        status = f"error: {e}"

    source.last_fetched_at = datetime.now(timezone.utc)
    source.last_status = status[:500]
    session.add(source)
    session.commit()
    return status


DEFAULT_SOURCES = [
    (
        "monosans/proxy-list",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    ),
    (
        "TheSpeedX/PROXY-List",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    ),
]


def seed_default_sources(session: Session) -> None:
    """Seed the verified starter sources on first startup. Idempotent."""
    for name, url in DEFAULT_SOURCES:
        existing = session.exec(select(ProxySource).where(ProxySource.url == url)).first()
        if existing is None:
            session.add(ProxySource(name=name, url=url))
    session.commit()
