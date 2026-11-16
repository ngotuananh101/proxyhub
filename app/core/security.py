import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# bcrypt hashes at most 72 bytes and refuses longer input outright (bcrypt
# >= 4 raises ValueError). Hash a digest instead of rejecting the user's
# password so long passphrases work.
BCRYPT_MAX_BYTES = 72


def _prepare(plain: str) -> bytes:
    """Encode a password to a bcrypt-safe byte string.

    Inputs above 72 bytes are hashed with SHA-256 first, then base64-encoded
    (44 bytes), so the full password contributes to the hash. The prefix keeps
    these digests from colliding with a raw password that happens to encode to
    the same bytes.
    """
    raw = plain.encode("utf-8")
    if len(raw) <= BCRYPT_MAX_BYTES:
        return raw
    return b"sha256:" + base64.b64encode(hashlib.sha256(raw).digest())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode())
    except (ValueError, TypeError):
        # Malformed stored hash or unusable input: treat as a failed login
        # rather than letting a 500 leak out of the auth path.
        return False


def create_access_token(data: dict, expires_delta: int | None = None) -> str:
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_TTL
        )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.APP_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.APP_KEY, algorithms=[settings.JWT_ALGORITHM])
