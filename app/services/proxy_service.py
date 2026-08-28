import random
from urllib.parse import urlparse

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


def import_proxies(session: Session, text: str) -> ImportResult:
    imported = 0
    duplicates = 0
    invalid: list[InvalidLine] = []

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = parse_proxy_line(line)
        if parsed is None:
            invalid.append(InvalidLine(line=line, reason="Invalid proxy URL format"))
            continue

        existing = session.exec(
            select(Proxy).where(
                Proxy.scheme == parsed["scheme"],
                Proxy.host == parsed["host"],
                Proxy.port == parsed["port"],
            )
        ).first()
        if existing:
            duplicates += 1
            continue

        proxy = Proxy(**parsed)
        session.add(proxy)
        imported += 1

    session.commit()
    return ImportResult(imported=imported, duplicates=duplicates, invalid=invalid)


def select_random_proxy(session: Session, tenant_id: int | None = None) -> Proxy | None:
    stmt = select(Proxy).where(
        Proxy.status == ProxyStatus.ALIVE,
        col(Proxy.scheme).in_(GATEWAY_SCHEMES),
    )
    if tenant_id is not None:
        stmt = stmt.where(Proxy.tenant_id == tenant_id)
    proxies = session.exec(stmt).all()
    if not proxies:
        return None
    return random.choice(proxies)
