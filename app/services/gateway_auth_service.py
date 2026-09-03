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

# Bcrypt verification LRU cache: (cred_id, sha256(password)) -> timestamp
_AUTH_CACHE: dict[tuple[int, str], float] = {}
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
                return True

    # Cache miss or expired: perform bcrypt verification
    valid = verify_password(password, cred.password_hash)

    if valid and ttl > 0:
        now = time.time()
        with _CACHE_LOCK:
            if len(_AUTH_CACHE) >= _MAX_CACHE_SIZE:
                # Evict oldest 10%
                sorted_keys = sorted(_AUTH_CACHE.keys(), key=lambda k: _AUTH_CACHE[k])
                for k in sorted_keys[: _MAX_CACHE_SIZE // 10]:
                    del _AUTH_CACHE[k]
            _AUTH_CACHE[cache_key] = now

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
