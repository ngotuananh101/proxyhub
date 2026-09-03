# Gateway Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement client authentication for the ProxyHub gateway (port 8899) supporting both HTTP Basic auth and IP whitelist (CIDR), combined session endpoint, gateway plugin changes, request log attribution, and frontend credentials management page.

**Architecture:** A new `gateway_credentials` table stores per-tenant credentials (`basic` or `ip_whitelist`). The gateway plugin extracts client credentials and posts to a single combined endpoint (`POST /internal/gateway/session`) that authenticates the client, selects an alive proxy scoped to the credential's tenant, and returns it in one round trip. Bcrypt password verification uses an in-process LRU cache with configurable TTL. The plugin handles 401 from session as HTTP 407 Proxy Authentication Required to the client. Request logs capture tenant_id, auth_credential_id, and auth_status.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy, Alembic, bcrypt, proxy.py 2.4.10, React, TanStack Query, shadcn/ui (base-sera), Vitest, Pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-gateway-auth-design.md`

## Global Constraints

- Python `>=3.10` features: union syntax `X | Y`, built-in generics `list[T]`, `dict[K, V]`.
- SQLModel table name: `gateway_credentials` verbatim.
- Auth modes: `basic` | `ip_whitelist` verbatim.
- Auth status: `allowed` | `denied` verbatim.
- Env var `GATEWAY_AUTH_CACHE_TTL` default `60.0`, added to `app/core/config.py` Settings (not `settings_registry.py`).
- Combined endpoint path: `POST /internal/gateway/session` guarded by `verify_internal_key(x_internal_key)`.
- 407 response header: `Proxy-Authenticate: Basic realm="ProxyHub"`.
- Password for basic auth: generated server-side (secrets.token_urlsafe(16)), returned plaintext ONCE in create/rotate response, never stored in plaintext, never returned in list/get.
- Foreign key `requestlogs.auth_credential_id` references `gateway_credentials.id` with `ON DELETE SET NULL`.
- Frontend design system: base-sera (square, border=0); never hand-edit generated `components/ui/` files.
- CIDR validation uses Python standard library `ipaddress` module; single IPs normalized to `/32` (v4) or `/128` (v6).
- All tests must pass: backend via `pytest`, frontend via `npm test` (vitest).

---

### Task 1: Model & Schema — GatewayCredential and RequestLog additions

**Files:**
- Create: `app/models/credential.py`
- Modify: `app/models/__init__.py:1-9`
- Modify: `app/models/log.py:7-22`
- Create: `app/schemas/credential.py`
- Modify: `app/schemas/log.py:4-15`
- Modify: `app/core/config.py:4-24`
- Test: `tests/test_credential_model.py`

**Interfaces:**
- Produces: `GatewayCredential` model (`id`, `tenant_id`, `name`, `auth_mode`, `username`, `password_hash`, `cidrs`, `is_active`, `last_used_at`, `created_at`), exported from `app.models`.
- Produces: `RequestLog` updated with `auth_credential_id: Optional[int]`, `auth_status: Optional[str]`.
- Produces: `GatewayCredentialCreate`, `GatewayCredentialUpdate`, `GatewayCredentialResponse`, `GatewayCredentialCreatedResponse` in `app.schemas.credential`.
- Produces: `RequestLogResponse` updated with `auth_credential_id: int | None`, `auth_status: str | None`.
- Produces: `settings.GATEWAY_AUTH_CACHE_TTL: float = 60.0`.

- [ ] **Step 1: Write the failing tests for GatewayCredential model & schemas**

Create `tests/test_credential_model.py`:

```python
import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.models.credential import AuthMode, GatewayCredential
from app.models.log import RequestLog
from app.models.tenant import Tenant
from app.schemas.credential import (
    GatewayCredentialCreate,
    GatewayCredentialResponse,
    GatewayCredentialUpdate,
)


def test_create_basic_credential_model(engine):
    with Session(engine) as session:
        tenant = Tenant(name="Test Tenant", slug="test-cred-tenant")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="test-basic",
            auth_mode=AuthMode.BASIC,
            username="bot1",
            password_hash="$2b$12$fakehashplaceholder",
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        assert cred.id is not None
        assert cred.tenant_id == tenant.id
        assert cred.auth_mode == "basic"
        assert cred.username == "bot1"
        assert cred.cidrs is None
        assert cred.is_active is True
        assert cred.last_used_at is None
        assert cred.created_at is not None


def test_create_ip_whitelist_credential_model(engine):
    with Session(engine) as session:
        tenant = Tenant(name="Test Tenant 2", slug="test-cred-tenant-2")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="test-ip",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.1.0/24,10.0.0.1/32",
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        assert cred.id is not None
        assert cred.auth_mode == "ip_whitelist"
        assert cred.username is None
        assert cred.password_hash is None
        assert "192.168.1.0/24" in cred.cidrs


def test_request_log_has_auth_fields(engine):
    with Session(engine) as session:
        log = RequestLog(
            client_ip="1.2.3.4",
            method="GET",
            host="example.com",
            auth_credential_id=42,
            auth_status="allowed",
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        assert log.auth_credential_id == 42
        assert log.auth_status == "allowed"


def test_schema_create_basic_validation():
    data = GatewayCredentialCreate(
        name="crawler",
        auth_mode="basic",
        username="user1",
    )
    assert data.auth_mode == "basic"
    assert data.username == "user1"


def test_schema_create_ip_whitelist_validation():
    data = GatewayCredentialCreate(
        name="office",
        auth_mode="ip_whitelist",
        cidrs="10.0.0.0/8, 192.168.1.1",
    )
    assert data.auth_mode == "ip_whitelist"


def test_schema_create_rejects_invalid_mode():
    with pytest.raises(ValidationError):
        GatewayCredentialCreate(name="bad", auth_mode="ldap")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_credential_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.credential'`

- [ ] **Step 3: Create GatewayCredential model**

Create `app/models/credential.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AuthMode:
    BASIC = "basic"
    IP_WHITELIST = "ip_whitelist"


class GatewayCredential(SQLModel, table=True):
    __tablename__ = "gateway_credentials"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    name: str
    auth_mode: str = Field(index=True)
    username: Optional[str] = Field(default=None, index=True)
    password_hash: Optional[str] = Field(default=None)
    cidrs: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    last_used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Update RequestLog model**

Modify `app/models/log.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class RequestLog(SQLModel, table=True):
    __tablename__ = "requestlogs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenants.id", index=True)
    auth_credential_id: Optional[int] = Field(
        default=None, foreign_key="gateway_credentials.id", index=True
    )
    auth_status: Optional[str] = Field(default=None)
    client_ip: Optional[str] = None
    method: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    response_bytes: Optional[int] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
```

- [ ] **Step 5: Export GatewayCredential in models `__init__.py`**

Modify `app/models/__init__.py`:

```python
from app.models.credential import AuthMode, GatewayCredential
from app.models.log import RequestLog
from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting
from app.models.source import ProxySource
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User

__all__ = [
    "User",
    "Proxy",
    "ProxyStatus",
    "AppSetting",
    "ProxySource",
    "RequestLog",
    "Tenant",
    "TenantMembership",
    "GatewayCredential",
    "AuthMode",
]
```

- [ ] **Step 6: Create credential schemas**

Create `app/schemas/credential.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class GatewayCredentialCreate(BaseModel):
    name: str
    auth_mode: Literal["basic", "ip_whitelist"]
    username: str | None = None
    cidrs: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Name cannot be empty")
        return s


class GatewayCredentialUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    cidrs: str | None = None
    rotate_password: bool = False


class GatewayCredentialResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    auth_mode: str
    username: str | None = None
    cidrs: str | None = None
    is_active: bool
    last_used_at: str | None = None
    created_at: str


class GatewayCredentialCreatedResponse(GatewayCredentialResponse):
    generated_password: str | None = None


class GatewayCredentialListResponse(BaseModel):
    items: list[GatewayCredentialResponse]
    total: int
```

- [ ] **Step 7: Update RequestLog schemas**

Modify `app/schemas/log.py`:

```python
from pydantic import BaseModel


class RequestLogResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    auth_credential_id: int | None = None
    auth_status: str | None = None
    client_ip: str | None = None
    method: str | None = None
    host: str | None = None
    path: str | None = None
    proxy_host: str | None = None
    proxy_port: int | None = None
    response_bytes: int | None = None
    created_at: str


class RequestLogListResponse(BaseModel):
    items: list[RequestLogResponse]
    total: int
    page: int
    size: int
```

- [ ] **Step 8: Add `GATEWAY_AUTH_CACHE_TTL` to Settings**

Modify `app/core/config.py`: add `GATEWAY_AUTH_CACHE_TTL: float = 60.0` to `class Settings(BaseSettings)` around line 18.

```python
    REQUEST_LOG_RETENTION_DAYS: int = 30
    GATEWAY_AUTH_CACHE_TTL: float = 60.0
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_credential_model.py -v`
Expected: 6 passed

- [ ] **Step 10: Commit**

```bash
git add app/models/credential.py app/models/__init__.py app/models/log.py app/schemas/credential.py app/schemas/log.py app/core/config.py tests/test_credential_model.py
git commit -m "feat(model): add GatewayCredential model, updated RequestLog and schemas"
```

---

### Task 2: Alembic Migration `0002` and Database Auto-patch

**Files:**
- Create: `alembic/versions/0002_add_gateway_credentials.py`
- Modify: `app/core/database.py:23-43`
- Modify: `tests/test_migration_resilience.py`

**Interfaces:**
- Produces: Alembic revision `0002` chained from `0001` creating `gateway_credentials` table and adding `auth_credential_id` + `auth_status` columns to `requestlogs`.
- Produces: `create_db_and_tables()` auto-patch logic for existing deployments missing `gateway_credentials` table or columns on `requestlogs`.

- [ ] **Step 1: Write test for database auto-patch resilience**

Modify `tests/test_migration_resilience.py`: add a test that creates legacy tables (pre-credentials) and asserts `create_db_and_tables()` patches them:

```python
def test_auto_patch_gateway_credentials(engine):
    from sqlalchemy import inspect
    from app.core.database import create_db_and_tables

    create_db_and_tables(engine)

    inspector = inspect(engine)
    assert inspector.has_table("gateway_credentials")

    log_cols = {c["name"] for c in inspector.get_columns("requestlogs")}
    assert "auth_credential_id" in log_cols
    assert "auth_status" in log_cols
```

- [ ] **Step 2: Run test to verify it fails (or passes partially)**

Run: `pytest tests/test_migration_resilience.py -v`
Expected: May fail if `create_db_and_tables()` doesn't patch existing tables without the new columns.

- [ ] **Step 3: Update `app/core/database.py` auto-patch**

Modify `create_db_and_tables` in `app/core/database.py`:

```python
def create_db_and_tables(target_engine=None):
    db_engine = target_engine or engine
    SQLModel.metadata.create_all(db_engine)

    # Ensure columns exist on existing tables if migrated from older schemas
    from sqlalchemy import inspect, text

    inspector = inspect(db_engine)
    tables_to_patch = ["proxies", "proxysources", "requestlogs"]
    for table_name in tables_to_patch:
        if inspector.has_table(table_name):
            cols = {c["name"] for c in inspector.get_columns(table_name)}
            if "tenant_id" not in cols:
                with db_engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN tenant_id INTEGER"
                        )
                    )

    # Patch requestlogs with gateway auth columns if missing
    if inspector.has_table("requestlogs"):
        cols = {c["name"] for c in inspector.get_columns("requestlogs")}
        if "auth_credential_id" not in cols:
            with db_engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE requestlogs ADD COLUMN auth_credential_id INTEGER")
                )
        if "auth_status" not in cols:
            with db_engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE requestlogs ADD COLUMN auth_status VARCHAR")
                )
```

- [ ] **Step 4: Create Alembic migration `0002_add_gateway_credentials.py`**

Create `alembic/versions/0002_add_gateway_credentials.py`:

```python
"""add gateway credentials

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("auth_mode", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("cidrs", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gateway_credentials_tenant_id", "gateway_credentials", ["tenant_id"])
    op.create_index("ix_gateway_credentials_auth_mode", "gateway_credentials", ["auth_mode"])
    op.create_index("ix_gateway_credentials_username", "gateway_credentials", ["username"])

    op.add_column(
        "requestlogs",
        sa.Column("auth_credential_id", sa.Integer(), sa.ForeignKey("gateway_credentials.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_requestlogs_auth_credential_id", "requestlogs", ["auth_credential_id"])
    op.add_column("requestlogs", sa.Column("auth_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("requestlogs", "auth_status")
    op.drop_index("ix_requestlogs_auth_credential_id", table_name="requestlogs")
    op.drop_column("requestlogs", "auth_credential_id")

    op.drop_index("ix_gateway_credentials_username", table_name="gateway_credentials")
    op.drop_index("ix_gateway_credentials_auth_mode", table_name="gateway_credentials")
    op.drop_index("ix_gateway_credentials_tenant_id", table_name="gateway_credentials")
    op.drop_table("gateway_credentials")
```

- [ ] **Step 5: Run tests to verify migration resilience**

Run: `pytest tests/test_migration_resilience.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/0002_add_gateway_credentials.py app/core/database.py tests/test_migration_resilience.py
git commit -m "feat(db): add alembic migration 0002 and database auto-patch for gateway credentials"
```

---

### Task 3: Gateway Auth Service — Bcrypt Cache & IP Whitelist Validation

**Files:**
- Create: `app/services/gateway_auth_service.py`
- Test: `tests/test_gateway_auth_service.py`

**Interfaces:**
- Produces: `validate_cidrs(cidrs_str: str) -> str` — validates and normalizes comma-separated CIDR strings using `ipaddress.ip_network`. Raises `ValueError` on invalid syntax. Normalizes bare IPs to `/32` (v4) or `/128` (v6).
- Produces: `ip_matches_cidrs(client_ip: str, cidrs_str: str | None) -> bool` — checks if `client_ip` falls within any CIDR in the comma-separated string. Returns `False` on empty/invalid.
- Produces: `verify_credential_password(cred: GatewayCredential, password: str) -> bool` — verifies password against bcrypt hash using in-process LRU cache (`(cred.id, sha256(password))` → timestamp) with TTL from `settings.GATEWAY_AUTH_CACHE_TTL`.
- Produces: `clear_auth_cache() -> None` — for testing / cache invalidation.
- Produces: `authenticate_gateway_request(session: Session, username: str | None, password: str | None, client_ip: str) -> GatewayCredential | None` — performs deterministic 2-step auth: Basic first, IP whitelist fallback. Returns matched `GatewayCredential` or `None`.

- [ ] **Step 1: Write failing tests for GatewayAuthService**

Create `tests/test_gateway_auth_service.py`:

```python
import time
from unittest.mock import patch
import pytest
from sqlmodel import Session

from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import Tenant
from app.services.gateway_auth_service import (
    authenticate_gateway_request,
    clear_auth_cache,
    ip_matches_cidrs,
    validate_cidrs,
    verify_credential_password,
)


def test_validate_cidrs_valid():
    result = validate_cidrs("192.168.1.0/24, 10.0.0.1, 2001:db8::/32")
    parts = [p.strip() for p in result.split(",")]
    assert "192.168.1.0/24" in parts
    assert "10.0.0.1/32" in parts  # normalized to /32
    assert "2001:db8::/32" in parts


def test_validate_cidrs_invalid():
    with pytest.raises(ValueError, match="Invalid CIDR"):
        validate_cidrs("not-an-ip")

    with pytest.raises(ValueError, match="Invalid CIDR"):
        validate_cidrs("999.999.999.999")


def test_validate_cidrs_empty():
    assert validate_cidrs("") == ""
    assert validate_cidrs("   ") == ""


def test_ip_matches_cidrs():
    cidrs = "192.168.1.0/24, 10.0.0.1/32"
    assert ip_matches_cidrs("192.168.1.55", cidrs) is True
    assert ip_matches_cidrs("10.0.0.1", cidrs) is True
    assert ip_matches_cidrs("10.0.0.2", cidrs) is False
    assert ip_matches_cidrs("8.8.8.8", cidrs) is False
    assert ip_matches_cidrs("invalid-ip", cidrs) is False
    assert ip_matches_cidrs("192.168.1.1", None) is False
    assert ip_matches_cidrs("192.168.1.1", "") is False


def test_bcrypt_cache_avoids_rehash(engine):
    clear_auth_cache()
    pw = "secret123"
    pw_hash = hash_password(pw)

    cred = GatewayCredential(
        id=1,
        tenant_id=1,
        name="test",
        auth_mode="basic",
        username="u1",
        password_hash=pw_hash,
    )

    # First call: hits bcrypt
    assert verify_credential_password(cred, pw) is True

    # Second call: hits cache (mock bcrypt to verify it's not called)
    with patch("app.services.gateway_auth_service.verify_password") as mock_verify:
        assert verify_credential_password(cred, pw) is True
        mock_verify.assert_not_called()

    # Wrong password: does not hit cache for correct password
    assert verify_credential_password(cred, "wrong") is False


def test_bcrypt_cache_ttl_expiry(engine):
    clear_auth_cache()
    pw = "secret123"
    pw_hash = hash_password(pw)

    cred = GatewayCredential(
        id=2,
        tenant_id=1,
        name="test",
        auth_mode="basic",
        username="u2",
        password_hash=pw_hash,
    )

    assert verify_credential_password(cred, pw) is True

    # Fast-forward time past TTL using mock
    with patch("app.services.gateway_auth_service.time.time", return_value=time.time() + 100):
        with patch("app.services.gateway_auth_service.verify_password", return_value=True) as mock_verify:
            assert verify_credential_password(cred, pw) is True
            mock_verify.assert_called_once()


def test_authenticate_basic_happy_path(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T1", slug="t1-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="basic-cred",
            auth_mode=AuthMode.BASIC,
            username="client1",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="client1",
            password="pass123",
            client_ip="1.2.3.4",
        )
        assert matched is not None
        assert matched.id == cred.id
        assert matched.tenant_id == t.id


def test_authenticate_basic_wrong_password(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T2", slug="t2-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="basic-cred2",
            auth_mode=AuthMode.BASIC,
            username="client2",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="client2",
            password="wrongpassword",
            client_ip="1.2.3.4",
        )
        assert matched is None


def test_authenticate_ip_whitelist_fallback(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T3", slug="t3-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="whitelist-cred",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.100.0/24",
            is_active=True,
        )
        session.add(cred)
        session.commit()

        # Request without basic auth but matching IP
        matched = authenticate_gateway_request(
            session=session,
            username=None,
            password=None,
            client_ip="192.168.100.42",
        )
        assert matched is not None
        assert matched.id == cred.id


def test_authenticate_inactive_credential_ignored(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T4", slug="t4-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="inactive-cred",
            auth_mode=AuthMode.BASIC,
            username="inactive_user",
            password_hash=hash_password("pass123"),
            is_active=False,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="inactive_user",
            password="pass123",
            client_ip="1.2.3.4",
        )
        assert matched is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gateway_auth_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.gateway_auth_service'`

- [ ] **Step 3: Implement `app/services/gateway_auth_service.py`**

Create `app/services/gateway_auth_service.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gateway_auth_service.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/gateway_auth_service.py tests/test_gateway_auth_service.py
git commit -m "feat(service): add gateway auth service with bcrypt cache and CIDR validation"
```

---

### Task 4: Combined Session Endpoint — `POST /internal/gateway/session`

**Files:**
- Modify: `app/api/internal.py:1-85`
- Test: `tests/test_gateway_session_endpoint.py`

**Interfaces:**
- Produces: `POST /internal/gateway/session` taking `GatewaySessionRequest` (`username: str | None`, `password: str | None`, `client_ip: str`), guarded by `X-Internal-Key`.
- Returns: `GatewaySessionResponse` (`tenant_id: int`, `credential_id: int`, `auth_mode: str`, `proxy: GatewaySessionProxy`, `default_target_url: str`).
- Returns: `401` on invalid credentials, `404` on no available proxy in tenant.
- Updates: `credential.last_used_at` timestamp on successful auth.
- Modifies: `receive_gateway_log` in `app/api/internal.py` to accept `auth_credential_id`, `auth_status`, `tenant_id` in `GatewayLogEntry`.

- [ ] **Step 1: Write failing tests for session endpoint**

Create `tests/test_gateway_session_endpoint.py`:

```python
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.proxy import Proxy, ProxyStatus
from app.models.tenant import Tenant
from app.services.gateway_auth_service import clear_auth_cache

INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def test_session_requires_internal_key(client):
    resp = client.post("/internal/gateway/session", json={"client_ip": "1.2.3.4"})
    assert resp.status_code == 401


def test_session_wrong_internal_key(client):
    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "1.2.3.4"},
        headers={"X-Internal-Key": "bad-key"},
    )
    assert resp.status_code == 401


def test_session_basic_auth_success(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot",
            auth_mode=AuthMode.BASIC,
            username="bot_user",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
        session.add(cred)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="10.20.30.40",
            port=8080,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_user", "password": "secret123", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == tenant.id
    assert data["credential_id"] == cred.id
    assert data["auth_mode"] == "basic"
    assert data["proxy"]["host"] == "10.20.30.40"
    assert data["proxy"]["port"] == 8080
    assert "default_target_url" in data

    # Verify last_used_at was updated
    with Session(engine) as session:
        updated_cred = session.get(GatewayCredential, cred.id)
        assert updated_cred.last_used_at is not None


def test_session_basic_auth_invalid_password_returns_401(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant B", slug="tenant-b")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot",
            auth_mode=AuthMode.BASIC,
            username="bot_user_2",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_user_2", "password": "wrong_password", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_session_ip_whitelist_success(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant C", slug="tenant-c")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="office-ip",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.10.0/24",
            is_active=True,
        )
        session.add(cred)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="10.20.30.50",
            port=3128,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "192.168.10.99"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == tenant.id
    assert data["auth_mode"] == "ip_whitelist"
    assert data["proxy"]["host"] == "10.20.30.50"


def test_session_no_available_proxy_returns_404(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant D", slug="tenant-d")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot_no_proxy",
            auth_mode=AuthMode.BASIC,
            username="bot_empty",
            password_hash=hash_password("pass"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_empty", "password": "pass", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No available proxy"


def test_log_entry_accepts_auth_fields(client, engine):
    resp = client.post(
        "/internal/logs",
        json={
            "client_ip": "1.2.3.4",
            "method": "CONNECT",
            "host": "google.com",
            "tenant_id": 1,
            "auth_credential_id": 7,
            "auth_status": "allowed",
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["auth_status"] == "allowed"
    assert data["auth_credential_id"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gateway_session_endpoint.py -v`
Expected: FAIL with `404 Not Found` on `/internal/gateway/session`

- [ ] **Step 3: Update `app/api/internal.py` with session endpoint and enriched log model**

Modify `app/api/internal.py`:

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import verify_internal_key
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.log import RequestLog
from app.schemas.log import RequestLogResponse
from app.schemas.proxy import InternalProxyResponse
from app.services.events import broadcast_sync
from app.services.gateway_auth_service import authenticate_gateway_request
from app.services.proxy_service import select_random_proxy
from app.services.settings_service import get_all as get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


# --- Legacy /internal/proxies (deprecated, kept for transition) ---

@router.get("/proxies", response_model=InternalProxyResponse)
def get_proxy_for_gateway(
    strategy: str = Query("random"),
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    verify_internal_key(x_internal_key)

    if strategy != "random":
        raise HTTPException(status_code=400, detail=f"Unsupported strategy: {strategy}")

    proxy = select_random_proxy(session)
    if proxy is None:
        raise HTTPException(status_code=404, detail="No available proxy")

    settings_values = get_settings(session)
    default_target = str(settings_values.get("HEALTH_CHECK_URL", "https://api.ipify.org"))

    return InternalProxyResponse(
        id=proxy.id,
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
        default_target_url=default_target,
    )


# --- Combined Gateway Session Endpoint ---

class GatewaySessionRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    client_ip: str


class GatewaySessionProxy(BaseModel):
    id: int
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class GatewaySessionResponse(BaseModel):
    tenant_id: int
    credential_id: int
    auth_mode: str
    proxy: GatewaySessionProxy
    default_target_url: str


@router.post("/gateway/session", response_model=GatewaySessionResponse)
def create_gateway_session(
    body: GatewaySessionRequest,
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    """Authenticate client and select an alive proxy for the credential's tenant in 1 round trip."""
    verify_internal_key(x_internal_key)

    cred = authenticate_gateway_request(
        session=session,
        username=body.username,
        password=body.password,
        client_ip=body.client_ip,
    )
    if cred is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Select proxy scoped to credential's tenant
    proxy = select_random_proxy(session, tenant_id=cred.tenant_id)
    if proxy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No available proxy")

    # Update last_used_at on credential
    cred.last_used_at = datetime.now(timezone.utc)
    session.add(cred)
    session.commit()

    settings_values = get_settings(session)
    default_target = str(settings_values.get("HEALTH_CHECK_URL", "https://api.ipify.org"))

    return GatewaySessionResponse(
        tenant_id=cred.tenant_id,
        credential_id=cred.id,
        auth_mode=cred.auth_mode,
        proxy=GatewaySessionProxy(
            id=proxy.id,
            scheme=proxy.scheme,
            host=proxy.host,
            port=proxy.port,
            username=proxy.username,
            password=proxy.password,
        ),
        default_target_url=default_target,
    )


# --- Enriched Access Log Receiver ---

class GatewayLogEntry(BaseModel):
    tenant_id: int | None = None
    auth_credential_id: int | None = None
    auth_status: str | None = None
    client_ip: str | None = None
    method: str | None = None
    host: str | None = None
    path: str | None = None
    proxy_host: str | None = None
    proxy_port: int | None = None
    response_bytes: int | None = None


@router.post("/logs", status_code=status.HTTP_201_CREATED)
def receive_gateway_log(
    body: GatewayLogEntry,
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    """Receive one access-log entry from the gateway plugin."""
    verify_internal_key(x_internal_key)

    log = RequestLog(**body.model_dump())
    session.add(log)
    session.commit()
    session.refresh(log)

    response = RequestLogResponse(
        id=log.id,
        tenant_id=log.tenant_id,
        auth_credential_id=log.auth_credential_id,
        auth_status=log.auth_status,
        client_ip=log.client_ip,
        method=log.method,
        host=log.host,
        path=log.path,
        proxy_host=log.proxy_host,
        proxy_port=log.proxy_port,
        response_bytes=log.response_bytes,
        created_at=utc_isoformat(log.created_at),
    )
    broadcast_sync("logs", response.model_dump())
    return response
```

- [ ] **Step 4: Run existing and new internal API tests**

Run: `pytest tests/test_internal_api.py tests/test_gateway_session_endpoint.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/internal.py tests/test_gateway_session_endpoint.py
git commit -m "feat(api): add combined POST /internal/gateway/session endpoint and enrich log receiver"
```

---

### Task 5: Management CRUD API — `/api/gateway-credentials`

**Files:**
- Create: `app/api/gateway_credentials.py`
- Modify: `app/main.py:1-60`
- Test: `tests/test_gateway_credentials_api.py`

**Interfaces:**
- Produces: `router` in `app/api/gateway_credentials.py` with:
  - `GET /api/gateway-credentials` — lists credentials for active tenant (scoped via `get_active_tenant_id`)
  - `POST /api/gateway-credentials` — creates credential, generates password for `basic`, validates CIDRs for `ip_whitelist`, gated by `require_tenant_role("admin")`
  - `PATCH /api/gateway-credentials/{id}` — updates name, is_active, cidrs, or rotates password, gated by `require_tenant_role("admin")`
  - `DELETE /api/gateway-credentials/{id}` — deletes credential row, gated by `require_tenant_role("admin")`
- Modifies: `app/main.py` to include `gateway_credentials_router`.

- [ ] **Step 1: Write failing tests for CRUD API**

Create `tests/test_gateway_credentials_api.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_access_token, hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def auth_headers(user: User, tenant_id: int | None = None) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = str(tenant_id)
    return headers


def test_list_credentials_requires_auth(client):
    resp = client.get("/api/gateway-credentials")
    assert resp.status_code == 401


def test_create_basic_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin1", email="a1@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 1", slug="t1-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "my-basic", "auth_mode": "basic", "username": "crawler1"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my-basic"
    assert data["auth_mode"] == "basic"
    assert data["username"] == "crawler1"
    assert "generated_password" in data
    assert len(data["generated_password"]) >= 16
    assert "password_hash" not in data


def test_create_duplicate_username_in_tenant_fails(client, engine):
    with Session(engine) as session:
        user = User(username="admin2", email="a2@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 2", slug="t2-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp1 = client.post(
        "/api/gateway-credentials",
        json={"name": "c1", "auth_mode": "basic", "username": "dup_user"},
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/gateway-credentials",
        json={"name": "c2", "auth_mode": "basic", "username": "dup_user"},
        headers=headers,
    )
    assert resp2.status_code == 409


def test_create_ip_whitelist_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin3", email="a3@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 3", slug="t3-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "office-net", "auth_mode": "ip_whitelist", "cidrs": "192.168.1.0/24, 10.0.0.1"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "office-net"
    assert data["auth_mode"] == "ip_whitelist"
    assert "192.168.1.0/24" in data["cidrs"]
    assert data["generated_password"] is None


def test_create_ip_whitelist_invalid_cidr_fails(client, engine):
    with Session(engine) as session:
        user = User(username="admin4", email="a4@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 4", slug="t4-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "bad-net", "auth_mode": "ip_whitelist", "cidrs": "not-valid-cidr"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_rotate_password_returns_new_password_once(client, engine):
    with Session(engine) as session:
        user = User(username="admin5", email="a5@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 5", slug="t5-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "to-rotate", "auth_mode": "basic", "username": "rot_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]
    old_pw = create_resp.json()["generated_password"]

    patch_resp = client.patch(
        f"/api/gateway-credentials/{cred_id}",
        json={"rotate_password": True},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["generated_password"] is not None
    assert data["generated_password"] != old_pw


def test_toggle_active_status(client, engine):
    with Session(engine) as session:
        user = User(username="admin6", email="a6@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 6", slug="t6-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "toggle-me", "auth_mode": "basic", "username": "tog_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/gateway-credentials/{cred_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


def test_delete_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin7", email="a7@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 7", slug="t7-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "to-del", "auth_mode": "basic", "username": "del_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/gateway-credentials/{cred_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify gone from list
    list_resp = client.get("/api/gateway-credentials", headers=headers)
    assert not any(c["id"] == cred_id for c in list_resp.json()["items"])


def test_member_cannot_create_or_delete(client, engine):
    with Session(engine) as session:
        user = User(username="member1", email="m1@test.com", password_hash=hash_password("pw"), is_admin=False)
        session.add(user)
        tenant = Tenant(name="Tenant 8", slug="t8-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

        membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=TenantRole.MEMBER)
        session.add(membership)
        session.commit()

    headers = auth_headers(user, tenant.id)

    # Member CAN list
    list_resp = client.get("/api/gateway-credentials", headers=headers)
    assert list_resp.status_code == 200

    # Member CANNOT create
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "forbidden", "auth_mode": "basic", "username": "forb"},
        headers=headers,
    )
    assert create_resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gateway_credentials_api.py -v`
Expected: FAIL with `404 Not Found` on `/api/gateway-credentials`

- [ ] **Step 3: Implement `app/api/gateway_credentials.py`**

Create `app/api/gateway_credentials.py`:

```python
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_active_tenant_id, get_current_user, require_tenant_role
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import TenantRole
from app.models.user import User
from app.schemas.credential import (
    GatewayCredentialCreate,
    GatewayCredentialCreatedResponse,
    GatewayCredentialListResponse,
    GatewayCredentialResponse,
    GatewayCredentialUpdate,
)
from app.services.gateway_auth_service import clear_auth_cache, validate_cidrs

router = APIRouter(prefix="/api/gateway-credentials", tags=["gateway-credentials"])


def _to_response(cred: GatewayCredential) -> GatewayCredentialResponse:
    return GatewayCredentialResponse(
        id=cred.id,
        tenant_id=cred.tenant_id,
        name=cred.name,
        auth_mode=cred.auth_mode,
        username=cred.username,
        cidrs=cred.cidrs,
        is_active=cred.is_active,
        last_used_at=utc_isoformat(cred.last_used_at) if cred.last_used_at else None,
        created_at=utc_isoformat(cred.created_at),
    )


@router.get("", response_model=GatewayCredentialListResponse)
def list_credentials(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """List all credentials for the active tenant."""
    query = (
        select(GatewayCredential)
        .where(GatewayCredential.tenant_id == tenant_id)
        .order_by(GatewayCredential.created_at.desc())
    )
    creds = session.exec(query).all()
    return GatewayCredentialListResponse(
        items=[_to_response(c) for c in creds],
        total=len(creds),
    )


@router.post("", response_model=GatewayCredentialCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_credential(
    body: GatewayCredentialCreate,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Create a new gateway credential. Server generates password for Basic auth."""
    generated_pw = None
    pw_hash = None
    normalized_cidrs = None

    if body.auth_mode == AuthMode.BASIC:
        if not body.username or not body.username.strip():
            raise HTTPException(status_code=422, detail="Username is required for Basic auth")
        username = body.username.strip()

        # Check unique username per tenant
        existing = session.exec(
            select(GatewayCredential).where(
                GatewayCredential.tenant_id == tenant_id,
                GatewayCredential.auth_mode == AuthMode.BASIC,
                GatewayCredential.username == username,
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{username}' already exists for this tenant",
            )

        generated_pw = secrets.token_urlsafe(16)
        pw_hash = hash_password(generated_pw)
    elif body.auth_mode == AuthMode.IP_WHITELIST:
        if not body.cidrs or not body.cidrs.strip():
            raise HTTPException(status_code=422, detail="CIDR list is required for IP whitelist")
        try:
            normalized_cidrs = validate_cidrs(body.cidrs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not normalized_cidrs:
            raise HTTPException(status_code=422, detail="At least one valid CIDR or IP is required")
        username = None
    else:
        raise HTTPException(status_code=422, detail=f"Invalid auth_mode: {body.auth_mode}")

    cred = GatewayCredential(
        tenant_id=tenant_id,
        name=body.name,
        auth_mode=body.auth_mode,
        username=username,
        password_hash=pw_hash,
        cidrs=normalized_cidrs,
        is_active=True,
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)

    resp = _to_response(cred)
    return GatewayCredentialCreatedResponse(
        **resp.model_dump(),
        generated_password=generated_pw,
    )


@router.patch("/{credential_id}", response_model=GatewayCredentialCreatedResponse)
def update_credential(
    credential_id: int,
    body: GatewayCredentialUpdate,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Update credential name, active status, CIDRs, or rotate password."""
    cred = session.get(GatewayCredential, credential_id)
    if not cred or cred.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential not found")

    generated_pw = None
    if body.name is not None:
        s = body.name.strip()
        if not s:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        cred.name = s

    if body.is_active is not None:
        cred.is_active = body.is_active
        clear_auth_cache()

    if body.cidrs is not None:
        if cred.auth_mode != AuthMode.IP_WHITELIST:
            raise HTTPException(status_code=422, detail="Cannot set CIDRs on basic auth credential")
        try:
            cred.cidrs = validate_cidrs(body.cidrs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if body.rotate_password:
        if cred.auth_mode != AuthMode.BASIC:
            raise HTTPException(status_code=422, detail="Cannot rotate password on IP whitelist credential")
        generated_pw = secrets.token_urlsafe(16)
        cred.password_hash = hash_password(generated_pw)
        clear_auth_cache()

    session.add(cred)
    session.commit()
    session.refresh(cred)

    resp = _to_response(cred)
    return GatewayCredentialCreatedResponse(
        **resp.model_dump(),
        generated_password=generated_pw,
    )


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: int,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Delete credential. Existing logs keep auth_credential_id (SET NULL)."""
    cred = session.get(GatewayCredential, credential_id)
    if not cred or cred.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential not found")

    session.delete(cred)
    session.commit()
    clear_auth_cache()
```

- [ ] **Step 4: Register router in `app/main.py`**

Modify `app/main.py`:
- Import: `from app.api.gateway_credentials import router as gateway_credentials_router`
- Register: `app.include_router(gateway_credentials_router)`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_gateway_credentials_api.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add app/api/gateway_credentials.py app/main.py tests/test_gateway_credentials_api.py
git commit -m "feat(api): add CRUD endpoints for gateway credentials"
```

---

### Task 6: Gateway Plugin — Session Call, 407 Response, Enriched Logs

**Files:**
- Modify: `app/gateway/plugin.py:1-208`
- Modify: `tests/test_gateway_plugin.py`

**Interfaces:**
- Produces: `RotateProxyPlugin` updated to:
  - Extract `Proxy-Authorization: Basic <b64>` from client request
  - Extract `client_ip` from `self.client.addr` (or context)
  - Post to `GATEWAY_SESSION_URL` (`username`, `password`, `client_ip`)
  - Parse nested `proxy` shape from `GatewaySessionResponse`
  - On `401` from session endpoint → write raw `407 Proxy Authentication Required` bytes to client, close connection, fire access log with `auth_status="denied"`
  - On `404` / error → write 502 to client, fire access log
  - Access log includes `tenant_id`, `auth_credential_id`, `auth_status`
- New env var: `GATEWAY_SESSION_URL` (defaults to `GATEWAY_API_URL.rsplit('/', 1)[0] + '/gateway/session'`)

- [ ] **Step 1: Write failing tests for updated Gateway Plugin**

Modify `tests/test_gateway_plugin.py`:

```python
from unittest.mock import MagicMock, patch
import pytest

from app.gateway.plugin import (
    RotateProxyPlugin,
    create_session_from_api,
    extract_basic_auth,
    build_407_response_bytes,
)


def test_extract_basic_auth():
    # Basic dXNlcjpwYXNz => user:pass
    header_val = b"Basic dXNlcjpwYXNz"
    u, p = extract_basic_auth(header_val)
    assert u == "user"
    assert p == "pass"


def test_extract_basic_auth_invalid():
    assert extract_basic_auth(b"Bearer xyz") == (None, None)
    assert extract_basic_auth(b"") == (None, None)
    assert extract_basic_auth(None) == (None, None)


def test_build_407_response_bytes():
    raw = build_407_response_bytes()
    assert b"407 Proxy Authentication Required" in raw
    assert b'Proxy-Authenticate: Basic realm="ProxyHub"' in raw


def test_create_session_from_api_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "tenant_id": 1,
        "credential_id": 10,
        "auth_mode": "basic",
        "proxy": {
            "id": 1,
            "scheme": "http",
            "host": "5.6.7.8",
            "port": 8080,
            "username": "u",
            "password": "p",
        },
        "default_target_url": "https://api.ipify.org",
    }

    with patch("app.gateway.plugin.httpx.post", return_value=mock_resp):
        endpoint, default_target, session_meta = create_session_from_api(
            session_url="http://test/internal/gateway/session",
            api_key="secret",
            client_ip="1.2.3.4",
            username="u",
            password="p",
        )
        assert endpoint is not None
        assert endpoint.hostname == b"5.6.7.8"
        assert endpoint.port == 8080
        assert session_meta["tenant_id"] == 1
        assert session_meta["credential_id"] == 10
        assert session_meta["auth_status"] == "allowed"


def test_create_session_from_api_401():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid credentials"

    with patch("app.gateway.plugin.httpx.post", return_value=mock_resp):
        endpoint, default_target, session_meta = create_session_from_api(
            session_url="http://test/internal/gateway/session",
            api_key="secret",
            client_ip="1.2.3.4",
        )
        assert endpoint is None
        assert session_meta["auth_status"] == "denied"
        assert session_meta["status_code"] == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gateway_plugin.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_session_from_api'`

- [ ] **Step 3: Update `app/gateway/plugin.py`**

Modify `app/gateway/plugin.py`:

```python
"""RotateProxyPlugin — proxy.py plugin that authenticates clients and fetches a proxy from ProxyHub backend per request."""
import base64
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import httpx
from proxy.common.constants import COLON
from proxy.common.utils import bytes_, text_
from proxy.core.base import TcpUpstreamConnectionHandler
from proxy.http import Url, httpHeaders
from proxy.http.exception import HttpProtocolException
from proxy.http.parser import HttpParser
from proxy.http.proxy import HttpProxyBasePlugin

logger = logging.getLogger(__name__)

GATEWAY_API_URL = os.environ.get("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
GATEWAY_SESSION_URL = os.environ.get(
    "GATEWAY_SESSION_URL", GATEWAY_API_URL.rsplit("/", 1)[0] + "/gateway/session"
)
GATEWAY_LOG_URL = os.environ.get(
    "GATEWAY_LOG_URL", GATEWAY_API_URL.rsplit("/", 1)[0] + "/logs"
)
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
API_TIMEOUT = 3.0

HTTP_407_RAW = (
    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
    b"Proxy-Authenticate: Basic realm=\"ProxyHub\"\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n\r\n"
)


def extract_basic_auth(header_val: Optional[bytes]) -> Tuple[Optional[str], Optional[str]]:
    """Extract (username, password) from Proxy-Authorization: Basic <b64> header."""
    if not header_val:
        return None, None
    try:
        parts = header_val.strip().split(b" ", 1)
        if len(parts) != 2 or parts[0].lower() != b"basic":
            return None, None
        decoded = base64.b64decode(parts[1]).decode("utf-8")
        if ":" in decoded:
            u, p = decoded.split(":", 1)
            return u, p
        return decoded, ""
    except Exception:
        return None, None


def build_407_response_bytes() -> bytes:
    """Raw 407 response bytes sent to client when authentication fails."""
    return HTTP_407_RAW


def create_session_from_api(
    session_url: str,
    api_key: str,
    client_ip: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Optional[Url], Optional[str], Dict[str, Any]]:
    """Call POST /internal/gateway/session to authenticate and get proxy in one round trip.

    Returns (Url, default_target_url, session_meta_dict).
    """
    payload: Dict[str, Any] = {"client_ip": client_ip}
    if username:
        payload["username"] = username
    if password:
        payload["password"] = password

    meta: Dict[str, Any] = {
        "tenant_id": None,
        "credential_id": None,
        "auth_status": "denied",
        "status_code": None,
    }

    try:
        resp = httpx.post(
            session_url,
            json=payload,
            headers={"X-Internal-Key": api_key},
            timeout=API_TIMEOUT,
        )
        meta["status_code"] = resp.status_code
    except Exception as e:
        logger.error("Failed to reach backend session API: %s", e)
        return None, None, meta

    if resp.status_code == 401:
        meta["auth_status"] = "denied"
        return None, None, meta

    if resp.status_code != 200:
        logger.warning("Backend session returned %d: %s", resp.status_code, resp.text)
        # Auth might have succeeded if 404 (no proxy), but still no usable proxy
        if resp.status_code == 404:
            meta["auth_status"] = "allowed"
        return None, None, meta

    data = resp.json()
    meta["tenant_id"] = data.get("tenant_id")
    meta["credential_id"] = data.get("credential_id")
    meta["auth_status"] = "allowed"

    proxy_data = data.get("proxy", {})
    auth = ""
    if proxy_data.get("username") and proxy_data.get("password"):
        auth = f"{proxy_data['username']}:{proxy_data['password']}@"
    url_str = f"{proxy_data['scheme']}://{auth}{proxy_data['host']}:{proxy_data['port']}"
    return Url.from_bytes(bytes_(url_str)), data.get("default_target_url"), meta


def send_access_log(payload: Dict[str, Any]) -> None:
    """POST one access-log entry to the backend. Fire-and-forget."""
    try:
        httpx.post(
            GATEWAY_LOG_URL,
            json=payload,
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Failed to send access log: %s", e)


class RotateProxyPlugin(TcpUpstreamConnectionHandler, HttpProxyBasePlugin):
    """Authenticates client via session endpoint and proxies through a tenant proxy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._endpoint: Optional[Url] = None
        self._default_target: Optional[str] = None
        self._metadata: List[Any] = [None, None, None, None]
        self._session_meta: Dict[str, Any] = {
            "tenant_id": None,
            "credential_id": None,
            "auth_status": "denied",
        }

    def handle_upstream_data(self, raw: memoryview) -> None:
        self.client.queue(raw)

    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        """Authenticate client and resolve proxy via backend session endpoint."""
        # Extract Proxy-Authorization from client if present
        raw_auth = None
        if request.has_header(b"proxy-authorization"):
            raw_auth = request.header(b"proxy-authorization")
        username, password = extract_basic_auth(raw_auth)

        # Extract client IP
        client_ip = "127.0.0.1"
        if hasattr(self.client, "addr") and self.client.addr:
            client_ip = str(self.client.addr[0])

        self._endpoint, self._default_target, self._session_meta = create_session_from_api(
            GATEWAY_SESSION_URL, INTERNAL_API_KEY, client_ip, username, password
        )

        # Handle 401 / auth denied: send 407 to client and abort
        if self._session_meta.get("auth_status") == "denied":
            self.client.queue(memoryview(build_407_response_bytes()))
            # Fire-and-forget access log for denied attempt
            self._fire_denied_log(request, client_ip)
            raise HttpProtocolException("Proxy authentication required")

        if self._endpoint is None:
            raise HttpProtocolException("No available proxy from ProxyHub backend")

        assert self._endpoint.hostname and self._endpoint.port
        endpoint_tuple = (text_(self._endpoint.hostname), self._endpoint.port)
        logger.info("Using upstream proxy %s:%s", *endpoint_tuple)

        self.initialize_upstream(*endpoint_tuple)
        assert self.upstream
        try:
            self.upstream.connect()
        except TimeoutError:
            raise HttpProtocolException(
                f"Timed out connecting to upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        except ConnectionRefusedError:
            raise HttpProtocolException(
                f"Connection refused by upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        return None

    def _fire_denied_log(self, request: HttpParser, client_ip: str) -> None:
        """Send access log entry for rejected authentication attempt."""
        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        method = None if not request.method else request.method.decode()

        threading.Thread(
            target=send_access_log,
            args=({
                "tenant_id": None,
                "auth_credential_id": None,
                "auth_status": "denied",
                "client_ip": client_ip,
                "method": method,
                "host": host,
                "path": path,
                "proxy_host": None,
                "proxy_port": None,
                "response_bytes": len(HTTP_407_RAW),
            },),
            daemon=True,
        ).start()

    def handle_client_request(self, request: HttpParser) -> Optional[HttpParser]:
        """Forward request to upstream proxy, stripping client auth and adding upstream auth."""
        if not self.upstream:
            return request

        # Strip client's Proxy-Authorization so upstream proxy doesn't see client creds
        if request.has_header(b"proxy-authorization"):
            request.del_header(b"proxy-authorization")

        # Direct gateway access rewrite
        if (
            self._default_target
            and not request.is_https_tunnel
            and (
                not request.has_header(b"host")
                or not request.path
                or not request.path.startswith(b"http://")
            )
        ):
            target_url = Url.from_bytes(bytes_(self._default_target))
            if target_url.hostname:
                target_port = target_url.port or (443 if target_url.scheme == b"https" else 80)
                request.add_header(
                    b"Host",
                    target_url.hostname
                    + (b":" + bytes_(str(target_port)) if target_url.port else b""),
                )
                request.path = bytes_(self._default_target)

        # Track metadata for access log
        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        method = None if not request.method else request.method.decode()
        self._metadata = [host, port, path, method]

        # Add upstream Proxy-Authorization header if upstream proxy has credentials
        if self._endpoint and self._endpoint.has_credentials:
            assert self._endpoint.username and self._endpoint.password
            request.add_header(
                httpHeaders.PROXY_AUTHORIZATION,
                b"Basic " + base64.b64encode(
                    self._endpoint.username + COLON + self._endpoint.password
                ),
            )

        self.upstream.queue(memoryview(request.build(for_proxy=True)))
        return request

    def handle_client_data(self, raw: memoryview) -> Optional[memoryview]:
        assert self.upstream
        self.upstream.queue(raw)
        return raw

    def handle_upstream_chunk(self, chunk: memoryview) -> Optional[memoryview]:
        if not self.upstream:
            return chunk
        raise Exception("handle_upstream_chunk should not be called")

    def on_upstream_connection_close(self) -> None:
        if self.upstream and not self.upstream.closed:
            self.upstream.close()
            self.upstream = None

    def on_access_log(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.upstream:
            return context
        addr, port = (self.upstream.addr[0], self.upstream.addr[1])
        context.update({
            "upstream_proxy_host": addr,
            "upstream_proxy_port": port,
            "server_host": self._metadata[0],
            "server_port": self._metadata[1],
            "request_path": self._metadata[2],
            "response_bytes": self.total_size,
        })
        logger.info(
            "%s:%s %s %s:%s%s -> %s:%s",
            context.get("client_ip"), context.get("client_port"),
            self._metadata[3], self._metadata[0], self._metadata[1],
            self._metadata[2] or "", addr, port,
        )
        threading.Thread(
            target=send_access_log,
            args=({
                "tenant_id": self._session_meta.get("tenant_id"),
                "auth_credential_id": self._session_meta.get("credential_id"),
                "auth_status": self._session_meta.get("auth_status", "allowed"),
                "client_ip": context.get("client_ip"),
                "method": self._metadata[3],
                "host": self._metadata[0],
                "path": self._metadata[2],
                "proxy_host": addr,
                "proxy_port": port,
                "response_bytes": self.total_size,
            },),
            daemon=True,
        ).start()
        return None
```

- [ ] **Step 4: Update `.env.example` with new gateway env vars**

Modify `.env.example`: add `GATEWAY_SESSION_URL` and `GATEWAY_AUTH_CACHE_TTL` entries.

- [ ] **Step 5: Run gateway plugin tests**

Run: `pytest tests/test_gateway_plugin.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/gateway/plugin.py tests/test_gateway_plugin.py .env.example
git commit -m "feat(gateway): update RotateProxyPlugin to use session endpoint and support 407 response"
```

---

### Task 7: Frontend API Client & GatewayCredentialsPage

**Files:**
- Create: `frontend/src/api/credentials.ts`
- Modify: `frontend/src/api/logs.ts:3-14`
- Create: `frontend/src/pages/GatewayCredentialsPage.tsx`
- Create: `frontend/src/components/credentials/CreateCredentialDialog.tsx`
- Create: `frontend/src/components/credentials/OneTimePasswordDialog.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx:26-34`
- Modify: `frontend/src/App.tsx:30-50`
- Modify: `frontend/src/pages/LogsPage.tsx:1-364`
- Test: `frontend/src/__tests__/credentials-page.test.tsx`

**Interfaces:**
- Produces: `frontend/src/api/credentials.ts` with `fetchCredentials`, `createCredential`, `updateCredential`, `deleteCredential`.
- Produces: route `/credentials` rendered inside `App.tsx` and sidebar link **Gateway** (`KeyRoundIcon`).
- Updates: `LogsPage.tsx` table with an "Auth Status" badge (green "allowed", red "denied").

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/__tests__/credentials-page.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import * as credentialsApi from '@/api/credentials'
import GatewayCredentialsPage from '@/pages/GatewayCredentialsPage'
import { TenantProvider } from '@/lib/tenant'

const mockCredentials = [
  {
    id: 1,
    tenant_id: 1,
    name: 'Scraper Bot',
    auth_mode: 'basic',
    username: 'scraper1',
    cidrs: null,
    is_active: true,
    last_used_at: '2026-08-29T10:00:00Z',
    created_at: '2026-08-20T10:00:00Z',
  },
  {
    id: 2,
    tenant_id: 1,
    name: 'Office Network',
    auth_mode: 'ip_whitelist',
    username: null,
    cidrs: '192.168.1.0/24',
    is_active: false,
    last_used_at: null,
    created_at: '2026-08-21T10:00:00Z',
  },
]

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>{ui}</BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  )
}

describe('GatewayCredentialsPage', () => {
  it('renders table with credentials', async () => {
    vi.spyOn(credentialsApi, 'fetchCredentials').mockResolvedValue({
      items: mockCredentials,
      total: 2,
    })

    renderWithProviders(<GatewayCredentialsPage />)

    await waitFor(() => {
      expect(screen.getByText('Scraper Bot')).toBeInTheDocument()
      expect(screen.getByText('Office Network')).toBeInTheDocument()
      expect(screen.getByText('scraper1')).toBeInTheDocument()
      expect(screen.getByText('192.168.1.0/24')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run: `npm --prefix frontend test credentials-page.test.tsx`
Expected: FAIL with missing modules

- [ ] **Step 3: Create `frontend/src/api/credentials.ts`**

Create `frontend/src/api/credentials.ts`:

```typescript
import client from './client'

export interface CredentialItem {
  id: number
  tenant_id: number
  name: string
  auth_mode: 'basic' | 'ip_whitelist'
  username: string | null
  cidrs: string | null
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface CredentialListResponse {
  items: CredentialItem[]
  total: number
}

export interface CreateCredentialPayload {
  name: string
  auth_mode: 'basic' | 'ip_whitelist'
  username?: string
  cidrs?: string
}

export interface CreatedCredentialResponse extends CredentialItem {
  generated_password?: string | null
}

export interface UpdateCredentialPayload {
  name?: string
  is_active?: boolean
  cidrs?: string
  rotate_password?: boolean
}

export async function fetchCredentials(): Promise<CredentialListResponse> {
  const res = await client.get('/api/gateway-credentials')
  return res.data
}

export async function createCredential(
  payload: CreateCredentialPayload
): Promise<CreatedCredentialResponse> {
  const res = await client.post('/api/gateway-credentials', payload)
  return res.data
}

export async function updateCredential(
  id: number,
  payload: UpdateCredentialPayload
): Promise<CreatedCredentialResponse> {
  const res = await client.patch(`/api/gateway-credentials/${id}`, payload)
  return res.data
}

export async function deleteCredential(id: number): Promise<void> {
  await client.delete(`/api/gateway-credentials/${id}`)
}
```

- [ ] **Step 4: Update `frontend/src/api/logs.ts` interface**

Modify `frontend/src/api/logs.ts`: add `auth_credential_id` and `auth_status` to `LogItem`:

```typescript
export interface LogItem {
  id: number
  tenant_id?: number | null
  auth_credential_id?: number | null
  auth_status?: 'allowed' | 'denied' | null
  client_ip: string | null
  method: string | null
  host: string | null
  path: string | null
  proxy_host: string | null
  proxy_port: number | null
  response_bytes: number | null
  created_at: string
}
```

- [ ] **Step 5: Create `OneTimePasswordDialog.tsx`**

Create `frontend/src/components/credentials/OneTimePasswordDialog.tsx`:

```tsx
import { useState } from 'react'
import { CopyIcon, CheckIcon } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface OneTimePasswordDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  username?: string | null
  password?: string | null
}

export function OneTimePasswordDialog({
  open,
  onOpenChange,
  username,
  password,
}: OneTimePasswordDialogProps) {
  const [copied, setCopied] = useState(false)

  if (!password) return null

  const curlExample = `curl -x http://${username || 'user'}:${password}@<gateway-host>:8899 https://api.ipify.org`

  const handleCopy = () => {
    navigator.clipboard.writeText(password)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Save Gateway Password</DialogTitle>
          <DialogDescription>
            This password is only shown once. Store it securely — you will not be able to see it again.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2">
            <Input readOnly value={password} className="font-mono text-sm" />
            <Button variant="outline" size="icon" onClick={handleCopy}>
              {copied ? <CheckIcon className="size-4 text-green-500" /> : <CopyIcon className="size-4" />}
            </Button>
          </div>
          <div className="rounded bg-muted p-2 text-xs font-mono break-all text-muted-foreground">
            {curlExample}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 6: Create `CreateCredentialDialog.tsx`**

Create `frontend/src/components/credentials/CreateCredentialDialog.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { createCredential, CreatedCredentialResponse } from '@/api/credentials'
import { useToast } from '@/components/ui/toast'

interface CreateCredentialDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccessCreated: (resp: CreatedCredentialResponse) => void
}

export function CreateCredentialDialog({
  open,
  onOpenChange,
  onSuccessCreated,
}: CreateCredentialDialogProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [name, setName] = useState('')
  const [authMode, setAuthMode] = useState<'basic' | 'ip_whitelist'>('basic')
  const [username, setUsername] = useState('')
  const [cidrs, setCidrs] = useState('')

  const mutation = useMutation({
    mutationFn: createCredential,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] })
      onOpenChange(false)
      setName('')
      setUsername('')
      setCidrs('')
      onSuccessCreated(data)
    },
    onError: (err: any) => {
      toast({
        title: 'Failed to create credential',
        description: err.response?.data?.detail || 'An error occurred',
        variant: 'destructive',
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate({
      name,
      auth_mode: authMode,
      username: authMode === 'basic' ? username : undefined,
      cidrs: authMode === 'ip_whitelist' ? cidrs : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Gateway Credential</DialogTitle>
            <DialogDescription>
              Create credentials for client access to the gateway port.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="cred-name">Name</Label>
              <Input
                id="cred-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Scraper Bot or Office Network"
                required
              />
            </div>

            <div className="space-y-2">
              <Label>Authentication Type</Label>
              <RadioGroup
                value={authMode}
                onValueChange={(v) => setAuthMode(v as 'basic' | 'ip_whitelist')}
                className="flex gap-4"
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="basic" id="r-basic" />
                  <Label htmlFor="r-basic">Basic Auth</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="ip_whitelist" id="r-ip" />
                  <Label htmlFor="r-ip">IP Whitelist</Label>
                </div>
              </RadioGroup>
            </div>

            {authMode === 'basic' ? (
              <div className="space-y-2">
                <Label htmlFor="cred-username">Username</Label>
                <Input
                  id="cred-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. crawler1"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  A strong password will be generated automatically.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="cred-cidrs">Allowed IPs / CIDRs</Label>
                <Textarea
                  id="cred-cidrs"
                  value={cidrs}
                  onChange={(e) => setCidrs(e.target.value)}
                  placeholder="192.168.1.0/24&#10;10.0.0.1"
                  rows={3}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Enter one IP or CIDR per line or comma-separated.
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 7: Create `GatewayCredentialsPage.tsx`**

Create `frontend/src/pages/GatewayCredentialsPage.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRoundIcon, PlusIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import {
  fetchCredentials,
  updateCredential,
  deleteCredential,
  CredentialItem,
  CreatedCredentialResponse,
} from '@/api/credentials'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { CreateCredentialDialog } from '@/components/credentials/CreateCredentialDialog'
import { OneTimePasswordDialog } from '@/components/credentials/OneTimePasswordDialog'
import { useTenant } from '@/lib/tenant'

export default function GatewayCredentialsPage() {
  const { currentTenant } = useTenant()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [otpDialog, setOtpDialog] = useState<{ open: boolean; username?: string | null; password?: string | null }>({
    open: false,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['gateway-credentials', currentTenant?.id],
    queryFn: fetchCredentials,
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateCredential(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] }),
  })

  const rotateMutation = useMutation({
    mutationFn: (id: number) => updateCredential(id, { rotate_password: true }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] })
      setOtpDialog({ open: true, username: res.username, password: res.generated_password })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteCredential,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Gateway Credentials</h1>
          <p className="text-muted-foreground text-sm">
            Manage client authentication for gateway port 8899.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="mr-2 size-4" /> Add Credential
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <KeyRoundIcon className="size-4" /> Credentials List
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Identity / CIDR</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-6 text-muted-foreground">
                    Loading credentials...
                  </TableCell>
                </TableRow>
              ) : !data?.items?.length ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-6 text-muted-foreground">
                    No gateway credentials found. Create one to authenticate gateway traffic.
                  </TableCell>
                </TableRow>
              ) : (
                data.items.map((cred: CredentialItem) => (
                  <TableRow key={cred.id}>
                    <TableCell className="font-medium">{cred.name}</TableCell>
                    <TableCell>
                      <Badge variant={cred.auth_mode === 'basic' ? 'default' : 'secondary'}>
                        {cred.auth_mode === 'basic' ? 'Basic' : 'IP Whitelist'}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {cred.auth_mode === 'basic' ? cred.username : cred.cidrs}
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={cred.is_active}
                        onCheckedChange={(checked) =>
                          toggleActiveMutation.mutate({ id: cred.id, is_active: checked })
                        }
                      />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {cred.last_used_at ? new Date(cred.last_used_at).toLocaleString() : 'Never'}
                    </TableCell>
                    <TableCell className="text-right space-x-1">
                      {cred.auth_mode === 'basic' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Rotate Password"
                          onClick={() => rotateMutation.mutate(cred.id)}
                        >
                          <RefreshCwIcon className="size-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Delete"
                        onClick={() => {
                          if (confirm(`Delete credential "${cred.name}"?`)) {
                            deleteMutation.mutate(cred.id)
                          }
                        }}
                      >
                        <Trash2Icon className="size-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateCredentialDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccessCreated={(resp: CreatedCredentialResponse) => {
          if (resp.generated_password) {
            setOtpDialog({ open: true, username: resp.username, password: resp.generated_password })
          }
        }}
      />

      <OneTimePasswordDialog
        open={otpDialog.open}
        onOpenChange={(open) => setOtpDialog((prev) => ({ ...prev, open }))}
        username={otpDialog.username}
        password={otpDialog.password}
      />
    </div>
  )
}
```

- [ ] **Step 8: Update Sidebar navigation and App routes**

Modify `frontend/src/components/layout/AppSidebar.tsx`:
- Import `KeyRoundIcon` from `'lucide-react'`
- Add `{ to: '/credentials', label: 'Gateway', icon: KeyRoundIcon }` to `navItems` right after `/logs`.

Modify `frontend/src/App.tsx`:
- Import `GatewayCredentialsPage from './pages/GatewayCredentialsPage'`
- Add `<Route path="/credentials" element={<GatewayCredentialsPage />} />` under `ProtectedRoute`.

- [ ] **Step 9: Update `LogsPage.tsx` to display auth status badge**

Modify `frontend/src/pages/LogsPage.tsx`:
- In the table header, add an "Auth" column
- In the row cells, render a badge:
  - `auth_status === 'denied'` → red destructive badge `<Badge variant="destructive">denied</Badge>`
  - `auth_status === 'allowed'` → green / outline badge `<Badge variant="outline" className="text-green-600 border-green-600">allowed</Badge>`
  - otherwise empty / dash

- [ ] **Step 10: Run frontend tests**

Run: `npm --prefix frontend test`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/credentials.ts frontend/src/api/logs.ts frontend/src/pages/GatewayCredentialsPage.tsx frontend/src/components/credentials/ frontend/src/components/layout/AppSidebar.tsx frontend/src/App.tsx frontend/src/pages/LogsPage.tsx frontend/src/__tests__/credentials-page.test.tsx
git commit -m "feat(frontend): add GatewayCredentialsPage, API client, sidebar link, and log auth status badges"
```

---

### Task 8: Full System End-to-End & Integration Tests

**Files:**
- Create: `tests/test_gateway_auth_e2e.py`

**Interfaces:**
- Tests full flow: User creates credential → Gateway session authenticates client → Session updates last_used_at → Gateway sends enriched log → Backend persists log with `auth_status` and `auth_credential_id`.

- [ ] **Step 1: Write comprehensive end-to-end test**

Create `tests/test_gateway_auth_e2e.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import create_access_token, hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.log import RequestLog
from app.models.proxy import Proxy, ProxyStatus
from app.models.tenant import Tenant
from app.models.user import User

INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def test_full_gateway_auth_lifecycle(client, engine):
    # 1. Setup tenant, admin user, alive proxy
    with Session(engine) as session:
        user = User(username="superadmin", email="sa@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="E2E Tenant", slug="e2e-tenant")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="192.168.99.1",
            port=8080,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    token = create_access_token({"sub": str(user.id)})
    api_headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(tenant.id)}

    # 2. Admin creates a Basic credential via CRUD API
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "e2e-bot", "auth_mode": "basic", "username": "e2e_crawler"},
        headers=api_headers,
    )
    assert create_resp.status_code == 201
    cred_data = create_resp.json()
    cred_id = cred_data["id"]
    password = cred_data["generated_password"]

    # 3. Client connects through gateway -> gateway calls session endpoint with wrong password
    fail_session = client.post(
        "/internal/gateway/session",
        json={"username": "e2e_crawler", "password": "wrong", "client_ip": "1.2.3.4"},
        headers=INTERNAL_HEADERS,
    )
    assert fail_session.status_code == 401

    # Gateway logs the denied attempt
    log_denied = client.post(
        "/internal/logs",
        json={
            "client_ip": "1.2.3.4",
            "method": "CONNECT",
            "host": "secret.com",
            "auth_status": "denied",
        },
        headers=INTERNAL_HEADERS,
    )
    assert log_denied.status_code == 201

    # 4. Client connects with correct password -> gateway calls session endpoint
    ok_session = client.post(
        "/internal/gateway/session",
        json={"username": "e2e_crawler", "password": password, "client_ip": "1.2.3.4"},
        headers=INTERNAL_HEADERS,
    )
    assert ok_session.status_code == 200
    session_data = ok_session.json()
    assert session_data["tenant_id"] == tenant.id
    assert session_data["credential_id"] == cred_id
    assert session_data["proxy"]["host"] == "192.168.99.1"

    # Gateway logs the allowed request
    log_allowed = client.post(
        "/internal/logs",
        json={
            "tenant_id": tenant.id,
            "auth_credential_id": cred_id,
            "auth_status": "allowed",
            "client_ip": "1.2.3.4",
            "method": "GET",
            "host": "api.ipify.org",
            "proxy_host": "192.168.99.1",
            "proxy_port": 8080,
            "response_bytes": 500,
        },
        headers=INTERNAL_HEADERS,
    )
    assert log_allowed.status_code == 201

    # 5. Verify request logs persisted correctly
    with Session(engine) as session:
        logs = session.exec(select(RequestLog).order_by(RequestLog.id.desc())).all()
        assert len(logs) >= 2
        allowed_row = logs[0]
        assert allowed_row.auth_status == "allowed"
        assert allowed_row.auth_credential_id == cred_id
        assert allowed_row.tenant_id == tenant.id

        denied_row = logs[1]
        assert denied_row.auth_status == "denied"
        assert denied_row.auth_credential_id is None
```

- [ ] **Step 2: Run all backend tests**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gateway_auth_e2e.py
git commit -m "test(e2e): add full gateway auth lifecycle test"
```
