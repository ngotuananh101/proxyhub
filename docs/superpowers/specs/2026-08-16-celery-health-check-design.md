# ProxyHub — Part 2: Automated Celery Health Check (Design Spec)

- **Date:** 2026-08-16
- **Status:** Approved
- **Scope:** Part 2 of 6 in the roadmap (MVP, Health Check, Multi-tenant, Sticky Session, WebSocket Logs, Docker Compose)

## 1. Objectives

Periodically and automatically check the health of the entire proxy pool using Celery + Redis:

- Celery Beat triggers every **5 minutes** → worker checks each proxy via HTTP request.
- Each proxy is updated with `status` (`alive`/`dead`), `latency_ms`, `last_checked_at`.
- Dashboard has a **"Check now"** button to trigger manually (no need to wait for the cycle to complete).
- Gateway only selects `alive` proxies (as committed in the MVP spec: "In Part 2, gateway only selects `alive`").

### Key Decisions

| Decision | Choice |
|---|---|
| Task queue | Celery ≥ 5.4, broker/result backend is Redis (pre-installed on dev machine) |
| Schedule | Celery Beat, every 300 seconds (5 minutes) |
| Fan-out | Task `check_all_proxies` reads DB → dispatches one `check_proxy` task per proxy |
| Check target | Env var `HEALTH_CHECK_URL`, default `https://api.ipify.org` |
| Timeout | Env var `HEALTH_CHECK_TIMEOUT`, default 10 seconds |
| Checked schemes | Only `http`/`https` (gateway only uses these 2 schemes); `socks5` remains `unknown` |
| Windows | Worker/beat run with `--pool=solo` (Celery does not officially support Windows) |

## 2. Architecture

```
┌─────────────┐  every 5 min  ┌──────────────────────┐
│ Celery Beat │ ─────────────▶ │ check_all_proxies()  │  (task)
└─────────────┘                └──────────┬───────────┘
                                          │ read DB, fan-out
                                          ▼
┌─────────────────────────────┐   ┌──────────────────────┐
│ Dashboard                   │   │ check_proxy(id) × N  │  (task)
│ POST /api/proxies/check-all │──▶│                      │
│ (JWT, returns 202)          │   └──────────┬───────────┘
└─────────────────────────────┘              │ httpx GET HEALTH_CHECK_URL
                                             │ via proxy (timeout 10s)
                                             ▼
                              ┌──────────────────────────────┐
                              │ SQLite: status, latency_ms,  │
                              │ last_checked_at, updated_at  │
                              └──────────────────────────────┘
```

### Data Flow

1. **Beat** calls `check_all_proxies` on schedule.
2. `check_all_proxies` opens a session, fetches all proxies with scheme `http`/`https`, dispatches `check_proxy(proxy_id)` for each proxy, and returns the count of dispatched tasks.
3. `check_proxy(proxy_id)` opens its own session, calls `health_service.check_proxy()`:
   - Successful HTTP request (any status code that returns a response) → `status=alive`, `latency_ms` = request duration, `last_checked_at` = now.
   - Timeout / connection error / no response → `status=dead`, `latency_ms=None`, `last_checked_at` = now.
4. Commit each proxy independently — an error on one proxy does not affect others.

## 3. Detailed Changes

### 3.1 Config — `app/core/config.py`

Add 4 fields to `Settings` (keep `extra: "ignore"`):

| Field | Type | Default |
|---|---|---|
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/2` |
| `HEALTH_CHECK_URL` | `str` | `https://api.ipify.org` |
| `HEALTH_CHECK_TIMEOUT` | `float` | `10.0` |

`.env.example` already includes `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`; add `HEALTH_CHECK_URL` and `HEALTH_CHECK_TIMEOUT`.

### 3.2 Health service — `app/services/health_service.py` (new)

Pure, synchronous check logic, **independent of Celery** (to allow testing with standard pytest):

```python
@dataclass
class CheckResult:
    alive: bool
    latency_ms: float | None

def check_proxy(proxy: Proxy) -> CheckResult:
    """GET HEALTH_CHECK_URL via proxy using httpx, timeout HEALTH_CHECK_TIMEOUT.
    HTTP response received → alive; timeout/connection error → dead."""
```

- Use `httpx.Client(proxy=...)` with URL format `{scheme}://{user}:{pass}@{host}:{port}` (only include credentials when present).
- Catch all httpx exceptions → `CheckResult(alive=False, latency_ms=None)`.
- Measure latency using `time.perf_counter()` around the request.

### 3.3 Celery worker — `app/worker.py` (new)

```python
celery_app = Celery("proxyhub", broker=..., backend=...)
celery_app.conf.beat_schedule = {
    "check-all-proxies-every-5-min": {
        "task": "app.worker.check_all_proxies",
        "schedule": 300.0,
    }
}
```

- `check_all_proxies`: reads DB (separate session), filters scheme ∈ {http, https}, dispatches `check_proxy.delay(proxy_id)` for each, returns the count.
- `check_proxy(proxy_id)`: reads proxy by id (not found → log warning, return), calls `health_service.check_proxy`, updates 4 fields (`status`, `latency_ms`, `last_checked_at`, `updated_at`), commits.
- Each task creates its own `Session(engine)` — does not use FastAPI dependencies.

### 3.4 API trigger — `app/api/proxies.py`

```
POST /api/proxies/check-all   (requires JWT like other endpoints)
→ dispatch check_all_proxies.delay()
→ 202 Accepted, body {"detail": "Health check started", "task_id": "..."}
```

Import task from `app.worker` (lazy, avoiding Celery import when not needed — but since worker.py only initializes the Celery app, a direct import is safe).

### 3.5 Gateway only selects alive proxies — `app/services/proxy_service.py`

`select_random_proxy`: change condition from `Proxy.status != ProxyStatus.DEAD` to `Proxy.status == ProxyStatus.ALIVE`. This is a behavioral change committed in the MVP spec.

### 3.6 Frontend — "Check now" button

- `frontend/src/api/proxies.ts`: add `triggerCheckAll()` → `POST /api/proxies/check-all`.
- `frontend/src/pages/ProxiesPage.tsx`: add a "Check now" Button (icon `RefreshCw`) next to the Import/Add buttons on the toolbar. Click → call API → toast success "Health check request sent" (or toast error if API fails). Does not auto-refetch — user clicks table refresh as usual.

### 3.7 Operations

- `requirements.txt`: add `celery>=5.4.0`, `redis>=5.0.0`.
- `start-dev.bat`: add 2 blocks — Celery Worker (`celery -A app.worker.celery_app worker --loglevel=info --pool=solo`) and Celery Beat (`celery -A app.worker.celery_app beat --loglevel=info`), using venv like other blocks.
- README: update checklist `[x] Automated Celery Health Check`, add `HEALTH_CHECK_URL`/`HEALTH_CHECK_TIMEOUT` to the `.env` section.

## 4. Error Handling

| Scenario | Handling |
|---|---|
| Proxy timeout / connection refused | Mark as `dead`, record `last_checked_at`, do not retry within that cycle |
| Proxy deleted between dispatch and check | `check_proxy` does not find id → log warning, ignore |
| A task crashes | Only that task fails (Celery default); other proxies are still checked |
| SQLite lock when API + worker write concurrently | Already handled by WAL + `busy_timeout=5000ms` from Part 1 |
| Redis not running | Worker/beat cannot start — clear error reported in terminal (no extra handling) |
| Proxy scheme `socks5` | Skipped during health check (remains `unknown`), not selected by gateway since it is not `alive` |

## 5. Testing

- **Unit `health_service`** (mock httpx): successful response → alive + latency; timeout → dead; connection error → dead; proxy with credentials → proxy URL contains credentials.
- **Unit `proxy_service`**: `select_random_proxy` only returns `alive` proxies (does not return `unknown`/`dead`).
- **API `POST /api/proxies/check-all`**: mock `check_all_proxies.delay()` → 202 + task_id; missing JWT → 401.
- **Worker tasks**: test `check_all_proxies` dispatches exactly N tasks (mock `.delay`), `check_proxy` updates fields correctly (using test DB, mock `health_service`).
- Frontend: keep 3 existing tests passing; clean build.

## 6. Out of Scope

- Health check for `socks5` (requires `socksio`; deferred to later parts if needed).
- Retry/backoff when proxy is dead, auto-deletion of dead proxies.
- Settings page to configure `HEALTH_CHECK_URL` from UI.
- Real-time result updates on Dashboard (WebSocket — Part 5).
- Running Celery via Docker/WSL2 (Part 6 — Docker Compose).
