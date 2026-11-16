import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, tuple_
from sqlmodel import Session, col, select

from app.models.proxy import Proxy, ProxyStatus
from app.models.source import ProxySource
from app.services.proxy_service import parse_proxy_line

logger = logging.getLogger(__name__)

MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2MB

# A source can list tens of thousands of proxies. SQLite caps a statement at
# 32766 bound parameters and older builds at 999, so the dedupe lookup is
# chunked: 500 keys x 3 columns stays well under every dialect's limit.
EXISTING_LOOKUP_CHUNK = 500


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


def upsert_parsed(
    session: Session, parsed: list[dict], tenant_id: int | None
) -> tuple[int, int]:
    """Insert parsed proxies that are not already stored. Returns (imported, duplicates).

    Existing rows are looked up in chunks of `EXISTING_LOOKUP_CHUNK` instead of
    one SELECT per line: thousands of round-trips would keep the write
    transaction open long enough to starve the API's busy_timeout, and a single
    unbounded IN clause overflows the backend's bound-parameter limit.
    """
    if not parsed:
        return 0, 0

    existing_map: dict[tuple[str, str, int], Proxy] = {}
    keys = [(item["scheme"], item["host"], item["port"]) for item in parsed]
    for start in range(0, len(keys), EXISTING_LOOKUP_CHUNK):
        chunk = keys[start : start + EXISTING_LOOKUP_CHUNK]
        query = select(Proxy).where(
            tuple_(Proxy.scheme, Proxy.host, Proxy.port).in_(chunk)
        )
        if tenant_id is not None:
            query = query.where(Proxy.tenant_id == tenant_id)
        for proxy in session.exec(query).all():
            existing_map[(proxy.scheme, proxy.host, proxy.port)] = proxy

    imported = 0
    duplicates = 0
    now = datetime.now(timezone.utc)
    inserted: set[tuple[str, str, int]] = set()
    for item in parsed:
        key = (item["scheme"], item["host"], item["port"])
        # A key can repeat within one payload (manual import of a pasted list).
        # Without this guard both copies would be queued for INSERT.
        if key in inserted:
            duplicates += 1
            continue
        if key in existing_map:
            duplicates += 1
            proxy = existing_map[key]
            if proxy.status == ProxyStatus.DEAD:
                proxy.status = ProxyStatus.UNKNOWN
                proxy.updated_at = now
                session.add(proxy)
            continue
        session.add(Proxy(**item, tenant_id=tenant_id))
        inserted.add(key)
        imported += 1

    return imported, duplicates


def import_source_text(
    session: Session, text: str, tenant_id: int | None = None
) -> tuple[int, int]:
    """Import proxies from fetched text. Returns (imported, duplicates)."""
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

    imported, duplicates = upsert_parsed(session, parsed, tenant_id)
    session.commit()
    return imported, duplicates


def purge_old_dead_proxies(
    session: Session, retention_days: float, tenant_id: int | None = None
) -> int:
    """Delete proxies dead for longer than the retention period.

    Scoped to `tenant_id` when given: a fetch triggered by one tenant must
    never delete another tenant's proxies.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    condition = [
        Proxy.status == ProxyStatus.DEAD,
        col(Proxy.updated_at) < cutoff,
    ]
    if tenant_id is not None:
        condition.append(Proxy.tenant_id == tenant_id)
    result = session.exec(delete(Proxy).where(*condition))
    session.commit()
    return result.rowcount or 0


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
    session: Session,
    source: ProxySource,
    timeout: float,
    retention_days: float,
    tenant_id: int | None = None,
) -> str:
    """Fetch one source, import its proxies, record the outcome.

    Returns the status string stored on the source.
    """
    effective_tenant_id = tenant_id if tenant_id is not None else source.tenant_id
    try:
        text = asyncio.run(_download(source.url, timeout))
        imported, duplicates = import_source_text(session, text, tenant_id=effective_tenant_id)
        purged = purge_old_dead_proxies(
            session, retention_days, tenant_id=effective_tenant_id
        )
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
        "monosans/proxy-list - http",
        "https://cdn.jsdelivr.net/gh/monosans/proxy-list@main/proxies/http.txt",
    ),
    (
        "TheSpeedX/PROXY-List - http",
        "https://cdn.jsdelivr.net/gh/TheSpeedX/PROXY-List@master/http.txt",
    ),
    (
        "iplocate/free-proxy-list - http",
        "https://cdn.jsdelivr.net/gh/iplocate/free-proxy-list@main/protocols/http.txt",
    ),
    (
        "iplocate/free-proxy-list - https",
        "https://cdn.jsdelivr.net/gh/iplocate/free-proxy-list@main/protocols/https.txt",
    ),
    (
        "proxyscrape/free-proxy-list - http",
        "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/http/data.txt",
    ),
    (
        "proxyscrape/free-proxy-list - https",
        "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/https/data.txt",
    ),
    (
        "proxifly/free-proxy-list - http",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    ),
    (
        "proxifly/free-proxy-list - https",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt",
    ),
]


def seed_default_sources(session: Session, tenant_id: int | None = None) -> None:
    """Seed the verified starter sources on first startup. Idempotent."""
    for name, url in DEFAULT_SOURCES:
        existing = session.exec(
            select(ProxySource).where(ProxySource.url == url, ProxySource.tenant_id == tenant_id)
        ).first()
        if existing is None:
            # Check if there is an unassigned legacy row with the same url
            unassigned = session.exec(
                select(ProxySource).where(ProxySource.url == url, ProxySource.tenant_id.is_(None))
            ).first()
            if unassigned is not None:
                unassigned.tenant_id = tenant_id
                session.add(unassigned)
            else:
                session.add(ProxySource(name=name, url=url, tenant_id=tenant_id))
    session.commit()
