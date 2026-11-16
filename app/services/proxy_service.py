from urllib.parse import urlparse

import sqlalchemy as sa
from sqlmodel import Session, col, select

from app.models.proxy import Proxy, ProxyStatus
from app.schemas.proxy import ImportResult, InvalidLine

VALID_SCHEMES = {"http", "https", "socks5"}
GATEWAY_SCHEMES = {"http", "https"}  # socks5 not supported by gateway in MVP


def parse_proxy_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        parsed = urlparse(line)
    except Exception:
        return None
    if parsed.scheme not in VALID_SCHEMES:
        return None
    if not parsed.hostname or not parsed.port:
        return None
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username,
        "password": parsed.password,
    }


def import_proxies(session: Session, text: str, tenant_id: int | None = None) -> ImportResult:
    """Import a pasted list. Returns counts plus the lines that did not parse.

    Parsing stays per-line so invalid lines can be reported back to the user;
    the dedupe/insert step is shared with the source fetcher, which does it in
    bulk instead of one SELECT per line.
    """
    parsed: list[dict] = []
    invalid: list[InvalidLine] = []

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        item = parse_proxy_line(line)
        if item is None:
            invalid.append(InvalidLine(line=line, reason="Invalid proxy URL format"))
            continue
        parsed.append(item)

    # Imported lazily: source_service imports parse_proxy_line from this module.
    from app.services.source_service import upsert_parsed

    imported, duplicates = upsert_parsed(session, parsed, tenant_id)
    session.commit()
    return ImportResult(imported=imported, duplicates=duplicates, invalid=invalid)


def select_random_proxy(session: Session, tenant_id: int | None = None) -> Proxy | None:
    stmt = select(Proxy).where(
        Proxy.status == ProxyStatus.ALIVE,
        col(Proxy.scheme).in_(GATEWAY_SCHEMES),
    )
    if tenant_id is not None:
        stmt = stmt.where(Proxy.tenant_id == tenant_id)

    # Database-level random sampling avoiding loading entire proxy pool into memory
    stmt = stmt.order_by(sa.func.random()).limit(1)
    return session.exec(stmt).first()
