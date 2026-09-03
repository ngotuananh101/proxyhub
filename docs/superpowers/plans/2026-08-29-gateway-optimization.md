# Gateway Security & Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address all critical and major vulnerabilities and performance bottlenecks identified in the system audit: implement HTTP connection pooling and thread pooling in gateway plugin, O(1) LRU eviction in auth cache, CIDR count limits and input validation, database connection pooling, composite indexing, and database-level random proxy selection.

**Architecture:** 
1. `app/gateway/plugin.py`: Singleton `httpx.Client` with connection pooling, `ThreadPoolExecutor` for fire-and-forget access logs, reduced `API_TIMEOUT` to 1.0s.
2. `app/services/gateway_auth_service.py`: `collections.OrderedDict` for O(1) LRU cache eviction under lock, `MAX_CIDRS_PER_CREDENTIAL = 100` limit, input length validation.
3. `app/api/internal.py`: Input length bounds on `GatewaySessionRequest` (`username: max 255`, `client_ip: max 45`).
4. `app/core/database.py`: Proper SQLAlchemy `QueuePool` configuration (`pool_size=20`, `max_overflow=30`, `pool_pre_ping=True`) for PostgreSQL.
5. `app/services/proxy_service.py`: Database-level random selection `order_by(sa.func.random()).limit(1)` avoiding loading full proxy pool to RAM.
6. `alembic/versions/0003_add_composite_indexes.py`: Composite index for basic auth `(auth_mode, username, is_active)` and proxy selection `(tenant_id, status, scheme)`.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy, Alembic, httpx, proxy.py 2.4.10, Pytest.

**Spec / Audit Reference:** Audit findings documented in conversation (H-1, M-1, M-2, M-3, M-4, M-5, Performance Bottlenecks 1-7).

## Global Constraints

- Python `>=3.10` features: union syntax `X | Y`, built-in generics `list[T]`, `dict[K, V]`.
- All tests must pass: backend via `pytest`.
- SQLite compatibility must be preserved for tests (`StaticPool` in tests, standard `QueuePool` for Postgres).
- Maximum CIDR entries per credential: 100 verbatim.
- Gateway HTTP client timeout: 1.0s verbatim.
- Access log executor max workers: 10 verbatim.

---

### Task 1: Gateway Plugin — Connection Pooling, ThreadPoolExecutor, and Timeout Reduction

**Files:**
- Modify: `app/gateway/plugin.py:20-60, 200-220, 300-330`
- Modify: `tests/test_gateway_plugin.py`

**Interfaces:**
- Produces: `get_http_client() -> httpx.Client` singleton with `limits=httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0)`.
- Produces: `_LOG_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="access_log")` replacing individual `threading.Thread.start()` calls.
- Updates: `API_TIMEOUT = 1.0` (from 3.0s).

- [ ] **Step 1: Write tests for gateway plugin connection pool and log executor**

Modify `tests/test_gateway_plugin.py`: add tests for `get_http_client` and `_LOG_EXECUTOR` usage:

```python
def test_get_http_client_singleton():
    from app.gateway.plugin import get_http_client
    c1 = get_http_client()
    c2 = get_http_client()
    assert c1 is c2
    assert not c1.is_closed


def test_send_access_log_uses_executor():
    from unittest.mock import patch
    from app.gateway.plugin import RotateProxyPlugin

    plugin = RotateProxyPlugin.__new__(RotateProxyPlugin)
    plugin.upstream = MagicMock()
    plugin.upstream.addr = ("1.2.3.4", 80)
    plugin.total_size = 100
    plugin._metadata = ["example.com", 80, "/", "GET"]
    plugin._session_meta = {"tenant_id": 1, "credential_id": 2, "auth_status": "allowed"}

    with patch("app.gateway.plugin._LOG_EXECUTOR.submit") as mock_submit:
        plugin.on_access_log({"client_ip": "127.0.0.1", "client_port": 1234})
        assert mock_submit.called
```

- [ ] **Step 2: Update `app/gateway/plugin.py`**

Modify `app/gateway/plugin.py`:
1. Change `API_TIMEOUT = 1.0`
2. Add `from concurrent.futures import ThreadPoolExecutor`
3. Add `get_http_client()` singleton helper
4. Update `create_session_from_api` and `send_access_log` to use `get_http_client()`
5. Initialize `_LOG_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="access_log")`
6. Replace `threading.Thread(target=send_access_log, ...).start()` with `_LOG_EXECUTOR.submit(send_access_log, ...)` in `_fire_denied_log` and `on_access_log`.

- [ ] **Step 3: Run gateway plugin tests**

Run: `pytest tests/test_gateway_plugin.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/gateway/plugin.py tests/test_gateway_plugin.py
git commit -m "perf(gateway): add HTTP connection pooling, thread pool for logs, and reduce timeout to 1s"
```

---

### Task 2: Gateway Auth Service — O(1) OrderedDict LRU Cache & CIDR Count Limits

**Files:**
- Modify: `app/services/gateway_auth_service.py:15-120`
- Modify: `tests/test_gateway_auth_service.py`

**Interfaces:**
- Produces: `_AUTH_CACHE = OrderedDict()` with O(1) eviction via `_AUTH_CACHE.popitem(last=False)`.
- Produces: `MAX_CIDRS_PER_CREDENTIAL = 100` enforcement in `validate_cidrs`.
- Produces: Normalized IPv4-mapped IPv6 support in `ip_matches_cidrs`.

- [ ] **Step 1: Write failing tests for O(1) cache eviction and CIDR limits**

Modify `tests/test_gateway_auth_service.py`:

```python
def test_validate_cidrs_rejects_exceeding_max_limit():
    from app.services.gateway_auth_service import validate_cidrs, MAX_CIDRS_PER_CREDENTIAL
    too_many = ",".join([f"10.0.{i // 256}.{i % 256}" for i in range(MAX_CIDRS_PER_CREDENTIAL + 10)])
    with pytest.raises(ValueError, match="Too many CIDRs"):
        validate_cidrs(too_many)


def test_ip_matches_ipv4_mapped_ipv6():
    from app.services.gateway_auth_service import ip_matches_cidrs
    cidrs = "192.168.1.0/24"
    # ::ffff:192.168.1.50 is IPv4-mapped IPv6
    assert ip_matches_cidrs("::ffff:192.168.1.50", cidrs) is True


def test_lru_cache_eviction_is_ordered_dict():
    from app.services.gateway_auth_service import _AUTH_CACHE
    from collections import OrderedDict
    assert isinstance(_AUTH_CACHE, OrderedDict)
```

- [ ] **Step 2: Update `app/services/gateway_auth_service.py`**

Modify `app/services/gateway_auth_service.py`:
1. Use `from collections import OrderedDict`
2. Define `MAX_CIDRS_PER_CREDENTIAL = 100`
3. Define `_AUTH_CACHE: OrderedDict[tuple[int, str], float] = OrderedDict()`
4. In `validate_cidrs`: check `len(normalized) >= MAX_CIDRS_PER_CREDENTIAL` and raise `ValueError(f"Too many CIDRs (max {MAX_CIDRS_PER_CREDENTIAL})")`
5. In `ip_matches_cidrs`: normalize IPv4-mapped IPv6:
   ```python
   if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
       addr = addr.ipv4_mapped
   ```
6. In `verify_credential_password`:
   - On cache hit: `_AUTH_CACHE.move_to_end(cache_key)`
   - On cache insertion: if `len(_AUTH_CACHE) >= _MAX_CACHE_SIZE`: `_AUTH_CACHE.popitem(last=False)` (O(1)), then insert and `move_to_end`.

- [ ] **Step 3: Run auth service tests**

Run: `pytest tests/test_gateway_auth_service.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/services/gateway_auth_service.py tests/test_gateway_auth_service.py
git commit -m "perf(auth): implement O(1) OrderedDict LRU cache, CIDR limits, and IPv4-mapped IPv6 normalization"
```

---

### Task 3: Input Length Validation on Session Request & Internal API

**Files:**
- Modify: `app/api/internal.py:56-65`
- Modify: `tests/test_gateway_session_endpoint.py`

**Interfaces:**
- Produces: `GatewaySessionRequest` with `Field(max_length=255)` on username/password and `Field(max_length=45)` on client_ip.

- [ ] **Step 1: Write tests for input size limits on session request**

Modify `tests/test_gateway_session_endpoint.py`:

```python
def test_session_request_rejects_oversized_fields(client):
    resp = client.post(
        "/internal/gateway/session",
        json={"username": "a" * 300, "client_ip": "1.2.3.4"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 422

    resp_ip = client.post(
        "/internal/gateway/session",
        json={"client_ip": "a" * 60},
        headers=INTERNAL_HEADERS,
    )
    assert resp_ip.status_code == 422
```

- [ ] **Step 2: Update `app/api/internal.py`**

Modify `GatewaySessionRequest` in `app/api/internal.py`:

```python
from pydantic import BaseModel, Field


class GatewaySessionRequest(BaseModel):
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    client_ip: str = Field(..., max_length=45)
```

- [ ] **Step 3: Run session endpoint tests**

Run: `pytest tests/test_gateway_session_endpoint.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/api/internal.py tests/test_gateway_session_endpoint.py
git commit -m "sec(internal): enforce strict input length limits on GatewaySessionRequest"
```

---

### Task 4: Database Connection Pooling & SQLite Resilience

**Files:**
- Modify: `app/core/database.py:6-25`

**Interfaces:**
- Produces: `create_engine` with `poolclass=QueuePool`, `pool_size=20`, `max_overflow=30`, `pool_pre_ping=True`, `pool_recycle=3600` for non-SQLite databases. Keeps SQLite config intact.

- [ ] **Step 1: Update `app/core/database.py`**

Modify `app/core/database.py`:

```python
from sqlalchemy import event
from sqlalchemy.pool import QueuePool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

connect_args = {}
engine_kwargs = {}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    engine_kwargs.update({
        "poolclass": QueuePool,
        "pool_size": 20,
        "max_overflow": 30,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, **engine_kwargs)
```

- [ ] **Step 2: Run all database and migration tests**

Run: `pytest tests/test_migration_resilience.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add app/core/database.py
git commit -m "perf(db): configure robust QueuePool for PostgreSQL connections"
```

---

### Task 5: Database-Native Random Proxy Selection

**Files:**
- Modify: `app/services/proxy_service.py:68-80`
- Modify: `tests/test_proxy_service.py`

**Interfaces:**
- Produces: `select_random_proxy(session, tenant_id)` using `order_by(sa.func.random()).limit(1)` instead of `.all()` + `random.choice()`.

- [ ] **Step 1: Check existing tests for `select_random_proxy`**

Run: `pytest tests/test_proxy_service.py::TestSelectRandomProxy -v`
Ensure all 5 existing tests pass.

- [ ] **Step 2: Update `select_random_proxy` in `app/services/proxy_service.py`**

Modify `app/services/proxy_service.py`:

```python
import sqlalchemy as sa


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
```

- [ ] **Step 3: Run proxy service tests**

Run: `pytest tests/test_proxy_service.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add app/services/proxy_service.py
git commit -m "perf(proxy): use database-level random sampling for proxy selection"
```

---

### Task 6: Alembic Migration `0003` — Composite Indexes for Auth & Proxy Selection

**Files:**
- Create: `alembic/versions/0003_add_composite_indexes.py`

**Interfaces:**
- Produces: `ix_gateway_credentials_auth_username_active` on `gateway_credentials (auth_mode, username, is_active)`.
- Produces: `ix_proxies_tenant_status_scheme` on `proxies (tenant_id, status, scheme)`.

- [ ] **Step 1: Create `alembic/versions/0003_add_composite_indexes.py`**

Create `alembic/versions/0003_add_composite_indexes.py`:

```python
"""add composite indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

"""
from typing import Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index(
        "ix_gateway_credentials_auth_username_active",
        "gateway_credentials",
        ["auth_mode", "username", "is_active"],
    )
    op.create_index(
        "ix_proxies_tenant_status_scheme",
        "proxies",
        ["tenant_id", "status", "scheme"],
    )


def downgrade() -> None:
    op.drop_index("ix_proxies_tenant_status_scheme", table_name="proxies")
    op.drop_index("ix_gateway_credentials_auth_username_active", table_name="gateway_credentials")
```

- [ ] **Step 2: Run all backend tests to verify no regressions**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/0003_add_composite_indexes.py
git commit -m "perf(db): add alembic migration 0003 for composite indexes on auth and proxy selection"
```
