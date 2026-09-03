from collections import OrderedDict
import hashlib
import ipaddress
import logging
import threading
import time
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import verify_password
from app.models.credential import AuthMode, GatewayCredential

logger = logging.getLogger(__name__)

MAX_CIDRS_PER_CREDENTIAL = 100

# Bcrypt verification LRU cache using OrderedDict for O(1) eviction: (cred_id, sha256(password)) -> timestamp
_AUTH_CACHE: OrderedDict[tuple[int, str], float] = OrderedDict()
_CACHE_LOCK = threading.Lock()
_MAX_CACHE_SIZE = 10_000


def clear_auth_cache() -> None:
    with _CACHE_LOCK:
        _AUTH_CACHE.clear()


def validate_cidrs(cidrs_str: str) -> str:
    """Validate and normalize comma-separated CIDRs.

    Single IPs (e.g. 1.2.3.4) are normalized to /32 (v4) or /128 (v6).
    Raises ValueError on invalid syntax.
    Returns normalized comma-separated string.
    """
    if not cidrs_str or not cidrs_str.strip():
        return ""

    normalized = []
    for raw in cidrs_str.split(","):
        entry = raw.strip()
        if not entry:
            continue

        if len(normalized) >= MAX_CIDRS_PER_CREDENTIAL:
            raise ValueError(f"Too many CIDRs (max {MAX_CIDRS_PER_CREDENTIAL})")

        try:
            # Try as network first (e.g. 192.168.1.0/24)
            net = ipaddress.ip_network(entry, strict=False)
            normalized.append(str(net))
        except ValueError:
            # Try as single address (e.g. 1.2.3.4)
            try:
                addr = ipaddress.ip_address(entry)
                net = ipaddress.ip_network(f"{addr}/{32 if addr.version == 4 else 128}")
                normalized.append(str(net))
            except ValueError:
                raise ValueError(f"Invalid CIDR or IP address: {entry}")

    return ",".join(normalized)


def ip_matches_cidrs(client_ip: str, cidrs_str: str | None) -> bool:
    """Check if client_ip falls within any CIDR in the comma-separated string."""
    if not cidrs_str or not client_ip:
        return False

    try:
        addr = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return False

    # Normalize IPv4-mapped IPv6 to IPv4
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped

    for raw in cidrs_str.split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            net = ipaddress.ip_network(entry, strict=False)
            if addr in net:
                return True
        except ValueError:
            continue

    return False


def _hash_pw_for_cache(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_credential_password(cred: GatewayCredential, password: str) -> bool:
    """Verify password against cred.password_hash with in-process LRU cache."""
    if not cred.password_hash or cred.id is None:
        return False

    ttl = settings.GATEWAY_AUTH_CACHE_TTL
    cache_key = (cred.id, _hash_pw_for_cache(password))

    # Check cache if TTL > 0
    if ttl > 0:
        now = time.time()
        with _CACHE_LOCK:
            verified_at = _AUTH_CACHE.get(cache_key)
            if verified_at is not None and (now - verified_at) < ttl:
                _AUTH_CACHE.move_to_end(cache_key)
                return True

    # Cache miss or expired: perform bcrypt verification
    valid = verify_password(password, cred.password_hash)

    if valid and ttl > 0:
        now = time.time()
        with _CACHE_LOCK:
            # O(1) LRU eviction when cache capacity is reached
            if len(_AUTH_CACHE) >= _MAX_CACHE_SIZE:
                _AUTH_CACHE.popitem(last=False)
            _AUTH_CACHE[cache_key] = now
            _AUTH_CACHE.move_to_end(cache_key)

    return valid


def authenticate_gateway_request(
    session: Session,
    username: str | None,
    password: str | None,
    client_ip: str,
) -> GatewayCredential | None:
    """Deterministic 2-step authentication:

    1. Basic auth attempted first: find active basic cred matching username, verify password.
    2. IP whitelist fallback: iterate active ip_whitelist creds, check CIDR match against client_ip.
    Returns matched GatewayCredential or None.
    """
    # Step 1: Basic auth
    if username and password:
        query = select(GatewayCredential).where(
            GatewayCredential.auth_mode == AuthMode.BASIC,
            GatewayCredential.username == username,
            GatewayCredential.is_active == True,  # noqa: E712
        )
        creds = session.exec(query).all()
        for cred in creds:
            if verify_credential_password(cred, password):
                return cred

    # Step 2: IP whitelist fallback
    if client_ip:
        query = select(GatewayCredential).where(
            GatewayCredential.auth_mode == AuthMode.IP_WHITELIST,
            GatewayCredential.is_active == True,  # noqa: E712
        )
        whitelist_creds = session.exec(query).all()
        for cred in whitelist_creds:
            if ip_matches_cidrs(client_ip, cred.cidrs):
                return cred

    return None
