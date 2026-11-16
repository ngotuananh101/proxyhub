# Full Project Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 10 critical and 17 medium findings plus the cross-cutting optimizations from the project-wide audit, without regressing the 279 backend / 32 frontend tests.

**Architecture:** Work bottom-up: backend services (correctness) → backend security/concurrency → schema & tooling → frontend state isolation → frontend UX. Each task is independently testable and committed separately. Bulk-DB operations move from per-row loops to set-based SQL; tenant scoping becomes explicit at every layer.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy 2.x, Alembic, Celery, Redis, pytest; React 19 + TypeScript + TanStack Query + Vitest; Docker Compose, GitHub Actions.

**Spec:** `/mnt/Data/Ponta/proxyhub` audit report delivered 2026-11-16 (findings B1–B10, M1–M17, O1–O8). Finding IDs below refer to it.

## Global Constraints

- Answer the user in Vietnamese; all code, comments, commit messages and docs in English.
- Line length 100; `ruff check app/ tests/ scripts/ alembic/` must pass.
- Python `>=3.10` (no `match`-only syntax, no 3.12-only typing shortcuts).
- Every backend task ends with `pytest -q` green; every frontend task with `npm test` + `npx tsc --noEmit` green.
- Never weaken an existing assertion to make a new behaviour pass; update it only when the behaviour intentionally changed, and say so in the commit body.
- The local test venv lives at `/tmp/proxyhub-venv`; run backend commands as `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest ...`.
- Frontend tests need `NODE_OPTIONS=--localstorage-file=/tmp/vl.json` until Task 16 lands.

## Review Focus

- Empty and single-row inputs to every set-based query (no `IN ()`, no division by zero).
- Concurrent imports of the same proxy across tenants (unique-constraint and purge scope).
- The dashboard under a 50-tab load (DB pool exhaustion) and under steady log traffic (invalidate storms).
- A deployment built from a fresh clone: `alembic upgrade head` on an empty database must match `create_all`.
- Secrets left at `.env.example` values (must refuse to boot) and passwords over 72 bytes (must not 500).

---

### Task 1: Set-based DB operations and tenant-scoped purge

**Files:**
- Modify: `app/services/source_service.py:32-104`, `app/services/proxy_service.py:34-65`, `app/api/proxies.py:67-126,210-221`
- Test: `tests/test_source_service.py`, `tests/test_proxy_service.py`, `tests/test_proxies_api.py`

**Interfaces:**
- Produces: `purge_old_dead_proxies(session: Session, retention_days: float, tenant_id: int | None = None) -> int`
- Produces: `import_proxies(session: Session, text: str, tenant_id: int | None = None) -> ImportResult` (now delegates to bulk path, keeps signature)
- Produces: `EXISTING_LOOKUP_CHUNK = 500` module constant in `app/services/source_service.py`

- [ ] **Step 1: Write failing tests** in `tests/test_source_service.py`

```python
def test_purge_is_scoped_to_one_tenant(self, session):
    self._seed(session, ProxyStatus.DEAD, 8, "9.9.9.1", tenant_id=1)
    self._seed(session, ProxyStatus.DEAD, 8, "9.9.9.2", tenant_id=2)
    assert purge_old_dead_proxies(session, retention_days=7, tenant_id=1) == 1
    assert [p.host for p in session.exec(select(Proxy)).all()] == ["9.9.9.2"]

def test_import_source_text_handles_more_keys_than_sqlite_limit(self, session):
    text = "\n".join(f"10.0.{i // 250}.{i % 250}:{8000 + i % 1000}" for i in range(1200))
    imported, duplicates = import_source_text(session, text, tenant_id=1)
    assert (imported, duplicates) == (1200, 0)
```

Extend `self._seed` with a `tenant_id: int | None = None` keyword.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_source_service.py -q`
Expected: FAIL — `unexpected keyword argument 'tenant_id'`, and the 1200-row case raises `OperationalError`.

- [ ] **Step 3: Implement**

In `source_service.py`:
- Add `EXISTING_LOOKUP_CHUNK = 500` and process `keys` in slices of that size, running one query per slice and merging into `existing_map`.
- Add `tenant_id` parameter to `purge_old_dead_proxies`; when not `None` add `Proxy.tenant_id == tenant_id`; replace the load-and-delete loop with
  `session.exec(delete(Proxy).where(Proxy.status == ProxyStatus.DEAD, col(Proxy.updated_at) < cutoff, <tenant filter>))` and return `result.rowcount or 0`. Re-import `from sqlalchemy import delete`.
- Pass `tenant_id=effective_tenant_id` at the `fetch_and_import` call site (`:142`).

In `proxy_service.py`: rewrite `import_proxies` to build `parsed`/`invalid` exactly as now, then delegate the dedupe-and-insert to `import_source_text`'s logic by extracting a shared `upsert_parsed(session, parsed: list[dict], tenant_id: int | None) -> tuple[int, int]` in `source_service.py` and calling it from both. `import_proxies` returns `ImportResult(imported=…, duplicates=…, invalid=invalid)`.

In `app/api/proxies.py`: replace both delete loops with a single
`session.exec(delete(Proxy).where(Proxy.status == ProxyStatus.DEAD, Proxy.tenant_id == tenant_id))` and `delete(Proxy).where(Proxy.id.in_(body.ids), Proxy.tenant_id == tenant_id)`; add `.order_by(Proxy.id)` to `list_proxies` before `offset/limit`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_source_service.py tests/test_proxy_service.py tests/test_proxies_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services app/api/proxies.py tests/
git commit -m "fix: scope dead-proxy purge per tenant, batch proxy imports, use set-based deletes"
```

---

### Task 2: Make "Check now" actually force a cycle

**Files:**
- Modify: `app/api/proxies.py:107-110`
- Test: `tests/test_proxies_api.py`

**Interfaces:**
- Consumes: `check_all_proxies(force: bool = False)` from `app/worker.py:171`.

- [ ] **Step 1: Write failing test** in `tests/test_proxies_api.py`

```python
def test_check_all_forces_a_cycle(client, auth_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.api.proxies.check_all_proxies.delay",
        lambda *a, **kw: calls.append((a, kw)) or type("R", (), {"id": "t1"})(),
    )
    resp = client.post("/api/proxies/check-all", headers=auth_headers)
    assert resp.status_code == 202
    assert calls and calls[0][1].get("force") is True
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_proxies_api.py::test_check_all_forces_a_cycle -q`
Expected: FAIL — `calls[0][1]` is `{}`.

- [ ] **Step 3: Implement**

Change `check_all_proxies.delay()` to `check_all_proxies.delay(force=True)`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_proxies_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/proxies.py tests/test_proxies_api.py
git commit -m "fix: make Check now bypass the health-check interval gate"
```

---

### Task 3: Secret validation and bcrypt length handling

**Files:**
- Modify: `app/core/config.py:29-50`, `app/core/security.py:9-14`, `app/schemas/auth.py:14-17`
- Test: `tests/test_config.py`, `tests/test_security.py`

**Interfaces:**
- Produces: `raise_for_bcrypt_length(plain: str) -> None` in `app/core/security.py` raising `ValueError` when `len(plain.encode()) > 72`.
- Produces: `INSECURE_PLACEHOLDER_PREFIX = "change_me"` in `app/core/config.py`.

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
def test_rejects_env_example_placeholder_secrets():
    s = Settings(APP_KEY="change_me_to_a_random_secure_secret_key",
                 INTERNAL_API_KEY="change_me_to_a_random_internal_api_key")
    with pytest.raises(RuntimeError, match="APP_KEY, INTERNAL_API_KEY"):
        validate_secrets(s)
```

`tests/test_security.py`:
```python
def test_password_of_73_bytes_raises_clear_error():
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("a" * 73)

def test_verify_does_not_raise_for_over_long_input():
    hashed = hash_password("short-pass")
    assert verify_password("a" * 200, hashed) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_config.py::test_rejects_env_example_placeholder_secrets tests/test_security.py -q`
Expected: FAIL — validation passes; `verify_password` raises.

- [ ] **Step 3: Implement**

- `config.py`: treat any value equal to `""` or starting with `INSECURE_PLACEHOLDER_PREFIX` as unset.
- `security.py`: `hash_password` calls `raise_for_bcrypt_length` first; `verify_password` returns `False` when the input exceeds 72 bytes instead of raising.
- `schemas/auth.py`: `ChangePasswordRequest.new_password` gets `max_length=72`; `LoginRequest.password` gets `max_length=72` so an over-long login returns 422 rather than 500.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_config.py tests/test_security.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core app/schemas/auth.py tests/test_config.py tests/test_security.py
git commit -m "fix: reject .env.example placeholder secrets and handle >72-byte passwords"
```

---

### Task 4: WebSocket must not pin a DB connection, and must not put the JWT in logs

**Files:**
- Modify: `app/api/events.py`, `app/services/events.py:23-25`, `frontend/src/hooks/useRealtime.ts:29-44`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces: `ConnectionManager.connect(websocket: WebSocket, subprotocol: str | None = None) -> None`.
- `GET /ws/events` accepts the JWT either as the `Sec-WebSocket-Protocol` header (preferred) or the legacy `?token=` query parameter.

- [ ] **Step 1: Write failing tests** in `tests/test_events.py`

```python
def test_websocket_closes_the_session_before_streaming(client, engine, monkeypatch):
    closed = []
    real_close = Session.close
    monkeypatch.setattr(
        Session, "close", lambda self: closed.append(self) or real_close(self)
    )
    token = _make_token(engine)
    with client.websocket_connect("/ws/events", subprotocols=[token]) as ws:
        assert closed, "session must be closed before the socket starts streaming"
        ws.send_text("ping")

def test_websocket_accepts_token_as_subprotocol(client, engine):
    token = _make_token(engine)
    with client.websocket_connect("/ws/events", subprotocols=[token]) as ws:
        assert ws.accepted_subprotocol == token
```

Add a `_make_token(engine)` helper creating a `User` and returning `create_access_token({"sub": str(user.id)})`. Assert on `Session.close` rather than `pool.checkedout()`: the `engine` fixture uses `StaticPool`, which never reports a checkout count.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_events.py -q`
Expected: FAIL — `accepted_subprotocol` is `None` and the pool reports a checkout.

- [ ] **Step 3: Implement**

- `events.py`: read the token from `websocket.headers.get("sec-websocket-protocol")` first, fall back to the `token` query param. After the `User` lookup call `session.close()` (releases the pooled connection; the dependency's context manager tolerates a second close). Pass the token as `subprotocol` to `manager.connect` so `websocket.accept(subprotocol=...)` echoes it.
- `events.py` docstring: state the query-param form is deprecated because uvicorn logs query strings.
- `useRealtime.ts`: build the socket as `new WebSocket(urlWithoutToken, [token])`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_events.py -q`
Expected: PASS. Then `cd frontend && npx tsc --noEmit` — PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/events.py app/services/events.py frontend/src/hooks/useRealtime.ts tests/test_events.py
git commit -m "fix: release the DB connection during WebSocket sessions and carry the JWT as a subprotocol"
```

---

### Task 5: One query for stats broadcast, and tenant-correct credential auth

**Files:**
- Modify: `app/worker.py:98-114`, `app/services/gateway_auth_service.py:129-162`, `app/api/gateway_credentials.py:73-93`
- Test: `tests/test_worker.py`, `tests/test_gateway_auth_service.py`, `tests/test_gateway_credentials_api.py`

**Interfaces:**
- Produces: `GatewayCredential.username` unique across tenants for `auth_mode == "basic"` (application-enforced, plus migration `0004`).
- `_broadcast_stats` keeps its payload shape (`total/alive/dead/unknown`) so `tests/test_worker.py:329` stays valid, but computes it with a single `GROUP BY`.

- [ ] **Step 1: Write failing tests**

`tests/test_gateway_credentials_api.py`:
```python
def test_basic_username_is_unique_across_tenants(client, admin_headers, second_tenant_headers):
    r1 = client.post("/api/gateway-credentials", json={"name": "a", "auth_mode": "basic", "username": "shared"}, headers=admin_headers)
    assert r1.status_code == 201
    r2 = client.post("/api/gateway-credentials", json={"name": "b", "auth_mode": "basic", "username": "shared"}, headers=second_tenant_headers)
    assert r2.status_code == 409
```

`tests/test_worker.py`:
```python
def test_stats_broadcast_uses_single_group_by(engine):
    ...  # assert the payload equals {"total":3,"alive":1,"dead":2,"unknown":0} AND that exactly one SELECT hit Proxy
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_gateway_credentials_api.py -q`
Expected: FAIL — second create returns 201.

- [ ] **Step 3: Implement**

- `gateway_credentials.py` `create_credential`: drop `GatewayCredential.tenant_id == tenant_id` from the duplicate-username query so the check is global; keep the 409 detail text mentioning the username.
- `worker.py` `_broadcast_stats`: one `select(Proxy.status, func.count(Proxy.id)).group_by(Proxy.status)` and fill the four keys from the result.
- `gateway_auth_service.py`: document on `authenticate_gateway_request` that global username uniqueness makes step 1 unambiguous.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_worker.py tests/test_gateway_auth_service.py tests/test_gateway_credentials_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/worker.py app/services/gateway_auth_service.py app/api/gateway_credentials.py tests/
git commit -m "fix: make basic-auth usernames globally unique and compute stats in one query"
```

---

### Task 6: Tenant integrity — membership FK check, SQLite FK enforcement, cached tenant resolution

**Files:**
- Modify: `app/api/tenants.py:79-104`, `app/core/database.py:24-31`, `app/services/tenant_service.py:10-37`, `app/api/deps.py:44-78`
- Test: `tests/test_tenants_api.py`, `tests/test_tenant_scoping.py`

**Interfaces:**
- Produces: `ensure_default_tenant(session: Session) -> Tenant` documented as safe to call per request (cached, no unconditional UPDATEs).
- Produces: `resolve_active_tenant(session, user, requested_id) -> int` remains behind `get_active_tenant_id`.

- [ ] **Step 1: Write failing tests**

```python
def test_add_member_rejects_unknown_user(client, admin_headers, engine):
    tenant = _make_tenant(engine, "t1")
    resp = client.post(f"/api/tenants/{tenant.id}/members", json={"user_id": 999_999, "role": "member"}, headers=admin_headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_tenants_api.py -q`
Expected: FAIL — returns 201.

- [ ] **Step 3: Implement**

- `tenants.py` `add_member`: `session.get(User, body.user_id)` → 404 `"User not found"` before creating the membership.
- `database.py` `_set_sqlite_pragma`: add `PRAGMA foreign_keys=ON`.
- `tenant_service.py`: run the three legacy `UPDATE … WHERE tenant_id IS NULL` statements only when a row with `tenant_id IS NULL` exists (single cheap `SELECT 1 … LIMIT 1` per table, or one `UNION` query); skip `commit()` when nothing changed.
- `deps.py` `get_current_admin` unchanged; `get_active_tenant_id` calls `ensure_default_tenant` only in the admin-without-memberships branch (already the case) — add a comment stating that.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_tenants_api.py tests/test_tenant_scoping.py tests/test_tenant_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/tenants.py app/core/database.py app/services/tenant_service.py app/api/deps.py tests/
git commit -m "fix: validate membership users, enforce SQLite FKs, and stop re-running legacy tenant backfills"
```

---

### Task 7: Reuse one HTTP client for health checks; bound the access-log queue

**Files:**
- Modify: `app/services/health_service.py:21-30`, `app/gateway/plugin.py:33-35,144-155,216-240,325-339`
- Test: `tests/test_health_service.py`, `tests/test_gateway_plugin.py`

**Interfaces:**
- Produces: `async def check_proxy(proxy, url, timeout, client: httpx.AsyncClient | None = None) -> CheckResult` — reuses the passed client when given.
- Produces: `LOG_QUEUE_LIMIT = 1000` and `_LOG_SLOTS = threading.BoundedSemaphore(LOG_QUEUE_LIMIT)` in `app/gateway/plugin.py`.

- [ ] **Step 1: Write failing tests**

`tests/test_health_service.py`:
```python
@pytest.mark.anyio
async def test_check_proxy_uses_supplied_client():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200))
    await check_proxy(_proxy(), URL, TIMEOUT, client=client)
    client.get.assert_awaited_once()
```

`tests/test_gateway_plugin.py`:
```python
def test_access_log_drops_when_queue_is_full(monkeypatch):
    import app.gateway.plugin as plugin
    monkeypatch.setattr(plugin, "_LOG_SLOTS", threading.BoundedSemaphore(1))
    assert plugin.submit_access_log({"a": 1}) is True
    assert plugin.submit_access_log({"a": 2}) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_health_service.py tests/test_gateway_plugin.py -q`
Expected: FAIL — unexpected keyword `client`; `submit_access_log` missing.

- [ ] **Step 3: Implement**

- `health_service.py`: when `client` is `None`, keep the current per-call `AsyncClient` (tests rely on the constructor args); when supplied, call `client.get(url)` directly.
- `worker.py` `_check_all`: create one `httpx.AsyncClient(timeout=...)` for the cycle and pass it to every `check_proxy`, closing it in a `finally`.
- `plugin.py`: add `submit_access_log(payload) -> bool` that acquires `_LOG_SLOTS` non-blocking, submits a wrapper releasing the semaphore in `finally`, and returns `False` (with a rate-limited warning) when full. Replace both `_LOG_EXECUTOR.submit(...)` call sites.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_health_service.py tests/test_gateway_plugin.py tests/test_worker.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/health_service.py app/gateway/plugin.py app/worker.py tests/
git commit -m "perf: share one HTTP client per health-check cycle and bound the access-log queue"
```

---

### Task 8: Remove the legacy internal endpoint and report proxy shortage honestly

**Files:**
- Modify: `app/api/internal.py:24-52`, `app/gateway/plugin.py:121-129`, `app/schemas/proxy.py:62-69`, `.env.example:38`
- Test: `tests/test_internal_api.py`, `tests/test_gateway_plugin.py`

**Interfaces:**
- Removes `GET /internal/proxies` and `InternalProxyResponse`.
- `create_session_from_api` sets `meta["auth_status"] = "no_proxy"` (not `"allowed"`) on 404.

- [ ] **Step 1: Write failing tests**

```python
def test_legacy_internal_proxies_endpoint_is_gone(client):
    resp = client.get("/internal/proxies", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404

def test_missing_proxy_marks_session_as_no_proxy(monkeypatch):
    ...  # stub the httpx client to return 404; assert meta["auth_status"] == "no_proxy"
```

Delete `test_internal_returns_proxy` and `test_internal_requires_key`'s `/internal/proxies` target, retargeting them at `/internal/gateway/session`.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_internal_api.py tests/test_gateway_plugin.py -q`
Expected: FAIL — endpoint still 200/401; status reads `"allowed"`.

- [ ] **Step 3: Implement**

- Delete the legacy router block and `InternalProxyResponse` (plus its import).
- `plugin.py`: map 404 → `"no_proxy"`; `before_upstream_connection` gives `"denied"` the 407 and `"no_proxy"` the existing `"No available proxy"` `HttpProtocolException`.
- `.env.example`: drop `GATEWAY_API_URL` and point `GATEWAY_SESSION_URL` / `GATEWAY_LOG_URL` at the concrete URLs; keep reading `GATEWAY_API_URL` only as a default-derivation fallback in `plugin.py` (documented).

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_internal_api.py tests/test_gateway_plugin.py tests/test_gateway_auth_e2e.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/internal.py app/gateway/plugin.py app/schemas/proxy.py .env.example tests/
git commit -m "refactor: drop the deprecated /internal/proxies endpoint and stop logging proxy shortages as allowed"
```

---

### Task 9: A bootstrap Alembic baseline that matches the models

**Files:**
- Create: `alembic/versions/0000_baseline.py`, `alembic/versions/0004_model_parity.py`
- Modify: `alembic.ini`
- Test: `tests/test_migrations.py` (new)

**Interfaces:**
- `alembic upgrade head` on an empty database must produce a schema whose tables, indexes and unique constraints equal `SQLModel.metadata.create_all`.

- [ ] **Step 1: Write the failing test** `tests/test_migrations.py`

```python
def test_alembic_head_matches_sqlmodel_metadata(tmp_path):
    url = f"sqlite:///{tmp_path/'m.db'}"
    _run_alembic(url, "upgrade", "head")
    created = _introspect(create_engine(url))
    expected = _introspect(_fresh_create_all_engine())
    assert created == expected
```

`_introspect` returns `{table: {"columns": set, "indexes": set, "unique": set}}`. Compare a whitelist of tables (`users, appsettings, proxies, proxysources, requestlogs, tenants, tenant_memberships, gateway_credentials`) and ignore `alembic_version`.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_migrations.py -q`
Expected: FAIL — `no such table: proxies`.

- [ ] **Step 3: Implement**

- `0000_baseline.py`: `down_revision = None`, revision `"0000"`; creates `users`, `appsettings`, `proxies`, `proxysources`, `requestlogs` in their **pre-tenant** shape (no `tenant_id`, no `auth_*` columns) with the indexes `ix_users_username` (unique), `ix_users_email` (unique), `ix_appsettings_key` (unique), `ix_proxies_scheme`, `ix_proxies_host`, `ix_proxies_status`, `ix_proxysources_enabled`, `ix_requestlogs_created_at`.
- `0001_add_tenants.py`: set `down_revision = "0000"` (no other change).
- `0004_model_parity.py`: `down_revision = "0003"`; creates `uq_proxy_tenant_scheme_host_port` and the unique index `ix_gateway_credentials_auth_mode_username`; use `op.batch_alter_table` so SQLite can add the constraint.
- `alembic.ini`: add `prepend_sys_path = .` under `[alembic]`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_migrations.py -q` then
`PYTHONPATH=$PWD DB_URL=sqlite:////tmp/fresh.db APP_KEY=x INTERNAL_API_KEY=y /tmp/proxyhub-venv/bin/alembic upgrade head`
Expected: PASS and migrations apply cleanly.

- [ ] **Step 5: Commit**

```bash
git add alembic alembic.ini tests/test_migrations.py
git commit -m "feat: add an Alembic baseline so a fresh database can be migrated from scratch"
```

---

### Task 10: Migration scripts, CI scope, dev.py env precedence, Docker hardening

**Files:**
- Modify: `scripts/migrate_sqlite_to_postgres.py:20`, `.github/workflows/ci.yml:16,23,26`, `dev.py:84-108`, `Dockerfile`, `deploy/supervisor.conf`, `frontend/Dockerfile`
- Test: `tests/test_dev_py.py` (new), `tests/test_migrations.py`

**Interfaces:**
- Produces: `_load_env_file(path) -> dict[str, str]` that understands `export `, single/double quotes and `#` comments.
- Produces: `_python_env()` where **process environment wins** over `.env`.
- Produces: Docker image runs as unprivileged user `proxyhub`.

- [ ] **Step 1: Write failing tests**

`tests/test_dev_py.py`:
```python
def test_process_env_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DB_URL=from_file\n")
    monkeypatch.setenv("DB_URL", "from_shell")
    assert dev._load_and_merge(tmp_path / ".env")["DB_URL"] == "from_shell"

def test_dotenv_parses_quotes_export_and_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text('export APP_KEY="a#b"\n# comment\nNAME=plain # trailing\n')
    values = dev._load_env_file(p)
    assert values["APP_KEY"] == "a#b"
    assert values["NAME"] == "plain"
```

`scripts/migrate_sqlite_to_postgres.py`: extend `TABLES` to
`["tenants", "users", "tenant_memberships", "gateway_credentials", "appsettings", "proxies", "proxysources", "requestlogs"]` and skip a table whose source columns are a subset check fails (pre-tenant SQLite files).

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_dev_py.py -q`
Expected: FAIL — `AttributeError: module 'dev' has no attribute '_load_and_merge'`.

- [ ] **Step 3: Implement**

- `dev.py`: add `_parse_env_value(raw)` (strip quotes, cut trailing ` #…` when unquoted) and `_load_and_merge(path)` returning `{**_load_env_file(path), **os.environ}`; `_python_env()` delegates to it. Also fix `shutdown()` to `sys.exit(exit_code)` when triggered by a child exit, and on Windows try `taskkill /T /PID` without `/F` first, escalating after the 10 s wait.
- `ci.yml`: `ruff check app/ tests/ scripts/ alembic/`, `python-version: "3.14"`, and add a step `alembic upgrade head` against a throwaway SQLite URL (needs `APP_KEY`/`INTERNAL_API_KEY` env).
- `Dockerfile`: install build deps in one layer, `pip install` then `apt-get purge -y gcc libffi-dev && apt-get autoremove -y`; add `RUN useradd -r -u 1000 proxyhub && chown -R proxyhub:proxyhub /app`; `USER proxyhub`; `deploy/supervisor.conf` drop `user=root`.
- `frontend/Dockerfile`: replace `RUN npm ci || npm install` with `RUN npm ci` so a lockfile mismatch fails the build instead of silently resolving fresh dependencies. Leave the nginx stage untouched: the official image needs root to bind :80, and switching to `nginx-unprivileged` is out of scope (tracked in Review Focus below).

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest tests/test_dev_py.py tests/test_migrations.py -q`
Expected: PASS. Then `docker build -t proxyhub-test . && docker run --rm proxyhub-test id -u` → prints `1000`.

- [ ] **Step 5: Commit**

```bash
git add dev.py .github/workflows/ci.yml Dockerfile deploy/supervisor.conf scripts/ tests/
git commit -m "chore: align CI with production, harden the container, and fix dev.py env precedence"
```

---

### Task 11: Frontend tenant isolation

**Files:**
- Modify: `frontend/src/lib/auth.ts`, `frontend/src/api/client.ts:19-28`, `frontend/src/pages/LoginPage.tsx:22-28`, `frontend/src/pages/ProxiesPage.tsx:111`, `frontend/src/components/proxies/StatCards.tsx:20`, `frontend/src/pages/SourcesPage.tsx:49`, `frontend/src/pages/LogsPage.tsx:141`, `frontend/src/App.tsx:20-25,47`
- Test: `frontend/src/__tests__/tenant-context.test.tsx`, new `frontend/src/__tests__/tenant-isolation.test.tsx`

**Interfaces:**
- Produces: `clearSession(): void` in `frontend/src/lib/auth.ts` removing `access_token` **and** `selected_tenant_id`.
- Produces: `AdminRoute` component in `App.tsx` redirecting non-admins to `/`.

- [ ] **Step 1: Write failing tests**

```tsx
it('clears tenant selection on logout', () => {
  localStorage.setItem('access_token', 't')
  localStorage.setItem('selected_tenant_id', '2')
  clearSession()
  expect(localStorage.getItem('selected_tenant_id')).toBeNull()
})

it('scopes proxy queries by active tenant', async () => {
  // render ProxiesPage inside a tenant context with id 2; assert the
  // useQuery key contains 2
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && NODE_OPTIONS=--localstorage-file=/tmp/vl.json npx vitest run src/__tests__/tenant-isolation.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `auth.ts`: `clearSession()` clears both keys; `AppHeader` uses it; `client.ts` 401 handler uses it; `LoginPage` calls `clearSession()` before `setToken`.
- Query keys gain the tenant id: `['proxies', tenantId, page, pageSize, statusFilter, search]`, `['stats', tenantId]`, `['sources', tenantId]`, `['logs', tenantId, {…}]`; `invalidateQueries` calls keep the short prefix so they still match.
- `StatCards`, `SourcesPage`, `LogsPage`, `ProxiesPage` call `useTenant()` and use `activeTenant?.id`; queries get `enabled: activeTenant !== null` where the tenant id is required.
- `App.tsx`: wrap `/tenants` in `AdminRoute` that reads the `['me']` query and redirects non-admins.

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx tsc --noEmit && NODE_OPTIONS=--localstorage-file=/tmp/vl.json npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "fix: scope query caches by tenant and clear tenant state on logout"
```

---

### Task 12: Frontend bulk-selection safety and error feedback

**Files:**
- Modify: `frontend/src/pages/ProxiesPage.tsx:64-190`, `frontend/src/components/proxies/ProxyTable.tsx:38-40`, `frontend/src/pages/GatewayCredentialsPage.tsx:40-61,132`, `frontend/src/pages/LogsPage.tsx:165-198`
- Test: new `frontend/src/__tests__/proxies-selection.test.tsx`, `frontend/src/__tests__/logs-realtime.test.tsx`

**Interfaces:**
- `ProxyTable` receives `allSelected: boolean` and `someSelected: boolean` computed by the parent from the current page's ids.

- [ ] **Step 1: Write failing tests**

```tsx
it('clears the selection when the page changes', async () => { ... })
it('does not treat equal counts on another page as all-selected', async () => { ... })
it('cancels the pending log flush on unmount', () => { /* assert clearTimeout called */ })
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && NODE_OPTIONS=--localstorage-file=/tmp/vl.json npx vitest run src/__tests__/proxies-selection.test.tsx src/__tests__/logs-realtime.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `ProxiesPage`: `useEffect(() => setSelected(new Set()), [page, pageSize, statusFilter, search, activeTenant?.id])`; compute `const currentIds = data?.items.map(p => p.id) ?? []`, `allSelected = currentIds.length > 0 && currentIds.every(id => selected.has(id))`; pass both to `ProxyTable` and delete its internal count comparison.
- Wrap `handleDelete` / `handleDeleteSelected` in `try/catch` with an error toast and only mutate selection on success.
- `GatewayCredentialsPage`: add `onError` to all three mutations, and format `last_used_at` with `formatDateTime(cred.last_used_at, timezone)` from `useTimezone()`.
- `LogsPage`: keep the flush timer in a ref and clear it in a `useEffect` cleanup; coalesce non-live invalidations with a 1000 ms trailing debounce.

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx tsc --noEmit && NODE_OPTIONS=--localstorage-file=/tmp/vl.json npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "fix: reset proxy selection across pages, surface mutation errors, and tidy the log flush timer"
```

---

### Task 13: Make the frontend suite pass on Node ≥ 25

**Files:**
- Modify: `frontend/src/test-setup.ts`, `frontend/vite.config.ts`
- Test: the whole existing suite

**Interfaces:**
- `test-setup.ts` installs a `Storage` polyfill on `globalThis` when Node's own `localStorage` shadows jsdom's.

- [ ] **Step 1: Reproduce**

Run: `cd frontend && npx vitest run`
Expected: 22 failures with `Cannot read properties of undefined (reading 'clear')` on Node 26.

- [ ] **Step 2: Implement**

Add to `src/test-setup.ts` the in-memory `Storage` shim guarded by `typeof globalThis.localStorage === 'undefined'`, defined with `Object.defineProperty(..., { configurable: true, writable: true, value })`.

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run && npx vitest run && npx vitest run`
Expected: PASS three times (the suite was flaky before the shim).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/test-setup.ts
git commit -m "test: polyfill localStorage so the suite runs on Node 25+"
```

---

### Task 14: Remove dead nginx config and verify the whole suite

**Files:**
- Delete: `frontend/nginx-proxy.conf`
- Test: full backend + frontend suites, `ruff`, `oxlint`, build

- [ ] **Step 1: Confirm nothing references it**

Run: `grep -rn "nginx-proxy.conf" --include=* . | grep -v node_modules | grep -v '\.git/'`
Expected: only `docs/superpowers/plans/…`. If a Dockerfile references it, stop and wire it in instead of deleting.

- [ ] **Step 2: Delete and verify**

```bash
git rm frontend/nginx-proxy.conf
```

- [ ] **Step 3: Full verification**

```bash
PYTHONPATH=$PWD /tmp/proxyhub-venv/bin/python -m pytest -q
/tmp/proxyhub-venv/bin/ruff check app/ tests/ scripts/ alembic/
cd frontend && npx oxlint && npx tsc --noEmit && npx vitest run && npm run build
```
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/nginx-proxy.conf
git commit -m "chore: delete the unreferenced nginx reverse-proxy config"
```

---

## Self-Review

**Coverage:** B1→T1, B2→T2, B3→T9, B4→T1, B5→T4, B6→T3, B7→T3, B8→T11, B9→T12, B10→T13; M1→T1, M2→T1, M3→T1, M4→T4, M5→T10, M6→T10, M7→T10, M8→T5, M9→T6, M10→T11, M11→T12, M12→T12, M13→T12, M14→T10, M15→T14, M16→T7, M17→T8; O1→T7, O2/O3→T6, O4→T1, O5→T5, O6→T11, O7→T10, O8→T10.

**Not fixed, deliberately:** floating base-image tags (reproducibility is a policy decision, not a bug) and `frontend/Dockerfile` running nginx as root (the official image needs root to bind :80; fixing it means switching to `nginx-unprivileged`, out of scope for this pass). Both are called out in Task 10's notes.
