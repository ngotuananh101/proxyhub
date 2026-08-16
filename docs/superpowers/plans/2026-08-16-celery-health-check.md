# Celery Health Check (Part 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically check proxy pool health every 5 minutes using Celery + Redis, update `status`/`latency_ms`/`last_checked_at`, add a "Check now" button on the Dashboard, and ensure the gateway only selects `alive` proxies.

**Architecture:** Celery Beat calls task `check_all_proxies` every 300s → fan-out one `check_proxy` task per proxy → calls `health_service.check_proxy()` (httpx GET through proxy) → writes results to SQLite. Endpoint `POST /api/proxies/check-all` (JWT) dispatches the same task for manual triggers.

**Tech Stack:** Celery ≥5.4, redis-py ≥5.0, httpx (existing), SQLModel, FastAPI, React + TanStack Query + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-08-16-celery-health-check-design.md`

## Global Constraints

- Run on **native Windows**: Celery worker/beat must run with `--pool=solo`; all `.bat` files must have **CRLF** line endings.
- Never print secret values from `.env` (SECRET_KEY, INTERNAL_API_KEY) to output/logs.
- Dev services bind to `127.0.0.1`.
- Backend runs using venv: `venv\Scripts\python.exe`; backend tests: `venv\Scripts\python.exe -m pytest`.
- Frontend: `cd frontend && npm run ...`; shadcn base is **Base UI** (use `render` prop, do NOT use `asChild`; icons inside Button use `data-icon="inline-start|inline-end"`, do not add size classes; toast uses `toast.add({ type, title, description })`).
- Commit messages in English, conventional commits (`feat:`, `test:`, `chore:`, `docs:`). DO NOT `git push` — user pushes themselves.
- Existing backend tests: 59 passed before starting. Frontend tests: 3 passed (`npm run test` runs vitest).
- Proxy scheme `socks5` is NOT health checked (keeps `unknown`).
- `select_random_proxy` after Part 2 only returns `alive` proxies (behavior change committed in the MVP spec).

---

### Task 1: Config + dependencies (Celery, Redis, health check settings)

**Files:**
- Modify: `app/core/config.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: None (first task).
- Produces: `settings.CELERY_BROKER_URL`, `settings.CELERY_RESULT_BACKEND`, `settings.HEALTH_CHECK_URL`, `settings.HEALTH_CHECK_TIMEOUT` — subsequent tasks read these 4 fields.

- [ ] **Step 1: Read existing config test file**

Read `tests/test_config.py` to understand the Settings test pattern currently in use (fixtures, monkeypatch env, etc.). Write new tests following the exact same pattern.

- [ ] **Step 2: Write failing test for the 4 new fields**

Add to `tests/test_config.py` (keep existing tests intact):

```python
def test_celery_and_health_check_defaults(monkeypatch):
    # Clear env to use defaults
    for key in (
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "HEALTH_CHECK_URL",
        "HEALTH_CHECK_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.CELERY_BROKER_URL == "redis://localhost:6379/1"
    assert s.CELERY_RESULT_BACKEND == "redis://localhost:6379/2"
    assert s.HEALTH_CHECK_URL == "https://api.ipify.org"
    assert s.HEALTH_CHECK_TIMEOUT == 10.0
```

Note: If existing tests in the file use a different way to initialize `Settings` (e.g. not passing `_env_file=None`), adjust to match the pattern — the goal is to assert the 4 default values.

- [ ] **Step 3: Run test to verify it FAILS**

Run: `venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: New test FAILS (fields do not exist yet — `AttributeError` or assertion error).

- [ ] **Step 4: Add 4 fields to Settings**

Modify `app/core/config.py` — add 4 lines to the `Settings` class (after `CORS_ORIGINS`):

```python
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    HEALTH_CHECK_URL: str = "https://api.ipify.org"
    HEALTH_CHECK_TIMEOUT: float = 10.0
```

- [ ] **Step 5: Add dependencies to requirements.txt**

Add 2 lines to the end of `requirements.txt`:

```
celery>=5.4.0
redis>=5.0.0
```

Install:

Run: `venv\Scripts\pip.exe install -r requirements.txt`
Expected: Celery + redis (and transitive dependencies) successfully installed.

- [ ] **Step 6: Update .env.example**

In `.env.example`, add 2 lines to the `# Celery (Part 2)` block (after `CELERY_RESULT_BACKEND`):

```
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=10
```

- [ ] **Step 7: Run test to verify it PASSES**

Run: `venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add app/core/config.py requirements.txt .env.example tests/test_config.py
git commit -m "feat: add Celery and health check settings with dependencies"
```

---

### Task 2: Health service — pure proxy check logic (httpx)

**Files:**
- Create: `app/services/health_service.py`
- Test: `tests/test_health_service.py`

**Interfaces:**
- Consumes: `settings.HEALTH_CHECK_URL`, `settings.HEALTH_CHECK_TIMEOUT` (Task 1); `Proxy` model (`app/models/proxy.py`) with fields `scheme`, `host`, `port`, `username`, `password`.
- Produces:
  - `CheckResult` dataclass: `alive: bool`, `latency_ms: float | None`.
  - `check_proxy(proxy: Proxy) -> CheckResult` — synchronous function, NO dependency on Celery/DB session.
  - `build_proxy_url(proxy: Proxy) -> str` — proxy URL construction helper (exported for testing).

- [ ] **Step 1: Write failing test**

Create `tests/test_health_service.py`:

```python
from unittest.mock import MagicMock, patch

import httpx

from app.models.proxy import Proxy
from app.services.health_service import CheckResult, build_proxy_url, check_proxy


def _proxy(**kwargs) -> Proxy:
    defaults = {"scheme": "http", "host": "1.2.3.4", "port": 8080}
    return Proxy(**{**defaults, **kwargs})


class TestBuildProxyUrl:
    def test_without_credentials(self):
        assert build_proxy_url(_proxy()) == "http://1.2.3.4:8080"

    def test_with_credentials(self):
        proxy = _proxy(username="user", password="pass")
        assert build_proxy_url(proxy) == "http://user:pass@1.2.3.4:8080"


class TestCheckProxy:
    def test_alive_with_latency(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = check_proxy(_proxy())
        assert result.alive is True
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    def test_dead_on_timeout(self):
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.TimeoutException("timeout")
            )
            result = check_proxy(_proxy())
        assert result == CheckResult(alive=False, latency_ms=None)

    def test_dead_on_connect_error(self):
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.ConnectError("refused")
            )
            result = check_proxy(_proxy())
        assert result == CheckResult(alive=False, latency_ms=None)

    def test_any_http_response_counts_as_alive(self):
        # Working proxy = receives HTTP response, even 403/500 from target
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = check_proxy(_proxy())
        assert result.alive is True

    def test_client_receives_proxy_url_and_timeout(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            check_proxy(_proxy())
        _, kwargs = mock_client.call_args
        assert kwargs["proxy"] == "http://1.2.3.4:8080"
        assert kwargs["timeout"] == 10.0
```

- [ ] **Step 2: Run test to verify it FAILS**

Run: `venv\Scripts\python.exe -m pytest tests/test_health_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.health_service'`.

- [ ] **Step 3: Write implementation**

Create `app/services/health_service.py`:

```python
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.models.proxy import Proxy


@dataclass
class CheckResult:
    alive: bool
    latency_ms: float | None


def build_proxy_url(proxy: Proxy) -> str:
    if proxy.username and proxy.password:
        return f"{proxy.scheme}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
    return f"{proxy.scheme}://{proxy.host}:{proxy.port}"


def check_proxy(proxy: Proxy) -> CheckResult:
    """GET HEALTH_CHECK_URL via proxy. HTTP response received -> alive; error/timeout -> dead."""
    start = time.perf_counter()
    try:
        with httpx.Client(
            proxy=build_proxy_url(proxy), timeout=settings.HEALTH_CHECK_TIMEOUT
        ) as client:
            client.get(settings.HEALTH_CHECK_URL)
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(alive=True, latency_ms=round(latency_ms, 2))
    except Exception:
        return CheckResult(alive=False, latency_ms=None)
```

- [ ] **Step 4: Run test to verify it PASSES**

Run: `venv\Scripts\python.exe -m pytest tests/test_health_service.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/health_service.py tests/test_health_service.py
git commit -m "feat: add health service checking proxies via httpx"
```

---

### Task 3: Celery worker — `app/worker.py` with 2 tasks + beat schedule

**Files:**
- Create: `app/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `settings.CELERY_BROKER_URL`, `settings.CELERY_RESULT_BACKEND` (Task 1); `health_service.check_proxy` (Task 2); `engine` from `app.core.database`; `Proxy`, `ProxyStatus` from `app.models.proxy`.
- Produces:
  - `celery_app` — Celery instance named `"proxyhub"`, `beat_schedule` key `"check-all-proxies-every-5-min"` running task `"app.worker.check_all_proxies"` every `300.0` seconds.
  - Task `check_all_proxies()` → returns `int` (number of dispatched tasks).
  - Task `check_proxy_task(proxy_id: int)` → returns `str` (`"alive"`, `"dead"`, or `"not_found"`). Celery task name is `app.worker.check_proxy_task`.

- [ ] **Step 1: Write failing test**

Create `tests/test_worker.py`:

```python
from unittest.mock import patch

from sqlmodel import Session

from app.models.proxy import Proxy, ProxyStatus


def _seed(engine, proxies: list[Proxy]) -> list[int]:
    with Session(engine) as session:
        for p in proxies:
            session.add(p)
        session.commit()
        return [p.id for p in proxies]


class TestCheckAllProxies:
    def test_dispatches_one_task_per_http_proxy(self, engine):
        _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(scheme="https", host="2.2.2.2", port=443),
                Proxy(scheme="socks5", host="3.3.3.3", port=1080),
            ],
        )
        from app.worker import check_all_proxies, check_proxy_task

        with patch.object(check_proxy_task, "delay") as mock_delay:
            count = check_all_proxies()
        assert count == 2  # socks5 is skipped
        assert mock_delay.call_count == 2

    def test_empty_pool_dispatches_nothing(self, engine):
        from app.worker import check_all_proxies, check_proxy_task

        with patch.object(check_proxy_task, "delay") as mock_delay:
            count = check_all_proxies()
        assert count == 0
        mock_delay.assert_not_called()


class TestCheckProxyTask:
    def test_marks_alive(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_proxy_task

        [proxy_id] = _seed(
            engine, [Proxy(scheme="http", host="1.1.1.1", port=80)]
        )
        with patch(
            "app.worker.health_service.check_proxy",
            return_value=CheckResult(alive=True, latency_ms=123.45),
        ):
            result = check_proxy_task(proxy_id)

        assert result == "alive"
        with Session(engine) as session:
            proxy = session.get(Proxy, proxy_id)
            assert proxy.status == ProxyStatus.ALIVE
            assert proxy.latency_ms == 123.45
            assert proxy.last_checked_at is not None

    def test_marks_dead(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_proxy_task

        [proxy_id] = _seed(
            engine,
            [Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE)],
        )
        with patch(
            "app.worker.health_service.check_proxy",
            return_value=CheckResult(alive=False, latency_ms=None),
        ):
            result = check_proxy_task(proxy_id)

        assert result == "dead"
        with Session(engine) as session:
            proxy = session.get(Proxy, proxy_id)
            assert proxy.status == ProxyStatus.DEAD
            assert proxy.latency_ms is None
            assert proxy.last_checked_at is not None

    def test_missing_proxy_returns_not_found(self, engine):
        from app.worker import check_proxy_task

        assert check_proxy_task(99999) == "not_found"


class TestBeatSchedule:
    def test_schedule_configured(self):
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["check-all-proxies-every-5-min"]
        assert entry["task"] == "app.worker.check_all_proxies"
        assert entry["schedule"] == 300.0
```

**Important — DB in tests:** The tasks in `app/worker.py` access the engine via `_get_engine()` (indirection allowing it to be patched). Place the autouse fixture INSIDE `tests/test_worker.py` (not in conftest to avoid affecting other tests), importing `app.worker` before patching:

```python
@pytest.fixture(autouse=True)
def _worker_engine(engine, monkeypatch):
    import app.worker

    monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)
```

(The import inside the fixture runs before the test body so the patch is always effective; no need to check `sys.modules`.)

- [ ] **Step 2: Run test to verify it FAILS**

Run: `venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.worker'`.

- [ ] **Step 3: Write implementation**

Create `app/worker.py`:

```python
import logging
from datetime import datetime, timezone

from celery import Celery
from sqlmodel import Session, col, select

from app.core import database
from app.core.config import settings
from app.models.proxy import Proxy, ProxyStatus
from app.services import health_service

logger = logging.getLogger(__name__)

celery_app = Celery(
    "proxyhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.beat_schedule = {
    "check-all-proxies-every-5-min": {
        "task": "app.worker.check_all_proxies",
        "schedule": 300.0,
    }
}

CHECKABLE_SCHEMES = ("http", "https")


def _get_engine():
    """Indirection so tests can swap the engine for an in-memory DB."""
    return database.engine


@celery_app.task(name="app.worker.check_all_proxies")
def check_all_proxies() -> int:
    with Session(_get_engine()) as session:
        proxies = session.exec(
            select(Proxy).where(col(Proxy.scheme).in_(CHECKABLE_SCHEMES))
        ).all()
        proxy_ids = [p.id for p in proxies]
    for proxy_id in proxy_ids:
        check_proxy_task.delay(proxy_id)
    logger.info("Dispatched %d health check tasks", len(proxy_ids))
    return len(proxy_ids)


@celery_app.task(name="app.worker.check_proxy_task")
def check_proxy_task(proxy_id: int) -> str:
    with Session(_get_engine()) as session:
        proxy = session.get(Proxy, proxy_id)
        if proxy is None:
            logger.warning("Proxy %s not found, skipping", proxy_id)
            return "not_found"

        result = health_service.check_proxy(proxy)
        proxy.status = ProxyStatus.ALIVE if result.alive else ProxyStatus.DEAD
        proxy.latency_ms = result.latency_ms
        proxy.last_checked_at = datetime.now(timezone.utc)
        proxy.updated_at = datetime.now(timezone.utc)
        session.add(proxy)
        session.commit()
        return "alive" if result.alive else "dead"
```

Add an autouse fixture at the top of `tests/test_worker.py` (after imports) so all tests in the file use the in-memory engine:

```python
import pytest


@pytest.fixture(autouse=True)
def _worker_engine(engine, monkeypatch):
    """Point app.worker engine to the in-memory test DB."""
    import app.worker

    monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)
```

- [ ] **Step 4: Run test to verify it PASSES**

Run: `venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Run entire backend suite to ensure nothing is broken**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: All PASS (59 existing + new tests).

- [ ] **Step 6: Commit**

```bash
git add app/worker.py tests/test_worker.py
git commit -m "feat: add Celery worker with health check tasks and beat schedule"
```

---

### Task 4: Gateway selects only alive proxies

**Files:**
- Modify: `app/services/proxy_service.py`
- Test: `tests/test_proxy_service.py`

**Interfaces:**
- Consumes: `ProxyStatus` from `app.models.proxy`.
- Produces: `select_random_proxy(session)` returns only proxies with `status == ALIVE` and scheme ∈ {http, https}; returns `None` if none exist.

- [ ] **Step 1: Update tests for the new behavior**

In `tests/test_proxy_service.py`, class `TestSelectRandomProxy`:

Replace test `test_select_includes_unknown` with:

```python
    def test_select_excludes_unknown(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is None
```

Keep `test_select_excludes_dead`, `test_select_excludes_socks5`, `test_select_empty_pool` unchanged (they remain correct under the new behavior).

- [ ] **Step 2: Run test to verify it FAILS**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxy_service.py -v`
Expected: `test_select_excludes_unknown` FAILS (currently unknown is still selected).

- [ ] **Step 3: Change condition in select_random_proxy**

In `app/services/proxy_service.py`, update `select_random_proxy`:

```python
def select_random_proxy(session: Session) -> Proxy | None:
    proxies = session.exec(
        select(Proxy).where(
            Proxy.status == ProxyStatus.ALIVE,
            col(Proxy.scheme).in_(GATEWAY_SCHEMES),
        )
    ).all()
    if not proxies:
        return None
    return random.choice(proxies)
```

(Only change line `Proxy.status != ProxyStatus.DEAD` to `Proxy.status == ProxyStatus.ALIVE`.)

- [ ] **Step 4: Run test to verify it PASSES**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxy_service.py tests/test_internal_api.py tests/test_gateway_plugin.py -v`
Expected: All PASS. If `test_internal_api.py` or `test_gateway_plugin.py` has tests that seed `unknown`/`dead` proxies and expect them to be selected, update the seed to `status=ProxyStatus.ALIVE` to match the new behavior.

- [ ] **Step 5: Run entire backend suite**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/proxy_service.py tests/test_proxy_service.py tests/test_internal_api.py tests/test_gateway_plugin.py
git commit -m "feat: gateway selects only alive proxies"
```

(Omit test files from `git add` that did not need modifications.)

---

### Task 5: API endpoint `POST /api/proxies/check-all`

**Files:**
- Modify: `app/api/proxies.py`
- Test: `tests/test_proxies_api.py`

**Interfaces:**
- Consumes: task `check_all_proxies` from `app.worker` (Task 3); `get_current_user` from `app.api.deps`.
- Produces: `POST /api/proxies/check-all` — requires JWT; dispatches `check_all_proxies.delay()`; returns **202** with body `{"detail": "Health check started", "task_id": "<id>"}`.

- [ ] **Step 1: Write failing test**

Add to `tests/test_proxies_api.py`:

```python
def test_check_all_dispatches_task(client, auth_headers):
    with patch("app.api.proxies.check_all_proxies.delay") as mock_delay:
        mock_delay.return_value = "fake-task-id"
        resp = client.post("/api/proxies/check-all", headers=auth_headers)
    assert resp.status_code == 202
    data = resp.json()
    assert data["detail"] == "Health check started"
    assert data["task_id"] == "fake-task-id"
    mock_delay.assert_called_once()


def test_check_all_requires_auth(client):
    resp = client.post("/api/proxies/check-all")
    assert resp.status_code == 401
```

Add import at top of file: `from unittest.mock import patch`.

- [ ] **Step 2: Run test to verify it FAILS**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxies_api.py -v`
Expected: 2 new tests FAIL (404 or 405 — endpoint does not exist yet).

- [ ] **Step 3: Add endpoint**

In `app/api/proxies.py`:

Add import at top of file:

```python
from app.worker import check_all_proxies
```

Add endpoint (place BEFORE `@router.get("/{proxy_id}")` to prevent the `check-all` route from being caught by `{proxy_id}`):

```python
@router.post("/check-all", status_code=status.HTTP_202_ACCEPTED)
def trigger_check_all(_: User = Depends(get_current_user)):
    result = check_all_proxies.delay()
    return {"detail": "Health check started", "task_id": result.id}
```

- [ ] **Step 4: Run test to verify it PASSES**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxies_api.py -v`
Expected: All PASS.

- [ ] **Step 5: Run entire backend suite**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/proxies.py tests/test_proxies_api.py
git commit -m "feat: add POST /api/proxies/check-all to trigger health check"
```

---

### Task 6: Frontend — "Check now" button on Proxies page

**Files:**
- Modify: `frontend/src/api/proxies.ts`
- Modify: `frontend/src/pages/ProxiesPage.tsx`

**Interfaces:**
- Consumes: `POST /api/proxies/check-all` (Task 5) returns 202 + `{detail, task_id}`; axios client from `./client`; toast from `@/components/ui/toast`.
- Produces: `triggerCheckAll(): Promise<{ detail: string; task_id: string }>` in `frontend/src/api/proxies.ts`.

- [ ] **Step 1: Add API function**

In `frontend/src/api/proxies.ts`, add after `fetchStats`:

```typescript
export interface CheckAllResponse {
  detail: string
  task_id: string
}

export async function triggerCheckAll(): Promise<CheckAllResponse> {
  const res = await client.post('/api/proxies/check-all')
  return res.data
}
```

- [ ] **Step 2: Add button to ProxiesPage**

In `frontend/src/pages/ProxiesPage.tsx`:

Add imports:

```typescript
import { RefreshCwIcon } from 'lucide-react'
import { triggerCheckAll } from '@/api/proxies'  // merge into existing import from '@/api/proxies'
```

Add state and handler inside the component (alongside other state variables):

```typescript
const [checking, setChecking] = useState(false)

const handleCheckAll = async () => {
  setChecking(true)
  try {
    await triggerCheckAll()
    toast.add({
      type: 'success',
      title: 'Health check requested',
      description: 'Results will update in a few minutes.',
    })
  } catch {
    toast.add({
      type: 'error',
      title: 'Failed to request health check',
    })
  } finally {
    setChecking(false)
  }
}
```

Add button to the toolbar container `<div className="flex gap-2">` (place BEFORE the "Add Proxy" button):

```tsx
<Button variant="outline" onClick={handleCheckAll} disabled={checking}>
  <RefreshCwIcon data-icon="inline-start" />
  Check now
</Button>
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds, no TypeScript errors.

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && npm run test`
Expected: 3 tests PASS (no new tests added for the button — keep scope concise; adding button render tests is optional).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/proxies.ts frontend/src/pages/ProxiesPage.tsx
git commit -m "feat: add health check trigger button to proxies page"
```

---

### Task 7: Operations — start-dev.bat, README, .env.example

**Files:**
- Modify: `start-dev.bat`
- Modify: `README.md`

**Interfaces:**
- Consumes: `app.worker.celery_app` (Task 3); Celery env vars (Task 1).
- Produces: `start-dev.bat` launches additional Celery Worker + Beat; README reflects Part 2 completion.

- [ ] **Step 1: Add 2 Celery blocks to start-dev.bat**

In `start-dev.bat`, after the Gateway block (line `start "ProxyHub Gateway" ...`), add:

```bat
REM --- 4. Celery Worker: health check tasks (Windows can --pool=solo) ---
start "ProxyHub Celery Worker" cmd /k "venv\Scripts\celery.exe -A app.worker.celery_app worker --loglevel=info --pool=solo"

REM --- 5. Celery Beat: scheduler 5 phut/lan ---
start "ProxyHub Celery Beat" cmd /k "venv\Scripts\celery.exe -A app.worker.celery_app beat --loglevel=info"
```

Update the header line at the start of the script to reflect all components:

```bat
echo   ProxyHub - Khoi dong Backend + Frontend + Gateway + Celery
```

And add 2 lines to the summary echo block at the end of the script:

```bat
echo   Celery  : worker + beat (health check moi 5 phut)
```

**Important:** The `.bat` file must keep **CRLF** line endings. After editing, verify:

Run: `file start-dev.bat`
Expected: Contains `CRLF` (e.g. `with CRLF line terminators`). If it has `LF` or lacks CRLF, convert it back: `awk 'sub(/$/, "\r")' start-dev.bat > tmp && mv tmp start-dev.bat`.

- [ ] **Step 2: Update README**

In `README.md`:

1. Change the line `- [ ] Automated Celery Health Check` to `- [x] Automated Celery Health Check`.
2. In the `.env` section (around lines 226-235), add 2 lines to the Celery block if not already present:

```
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=10
```

3. In section `### 3. Health Check` (around line 278), ensure the description matches the new behavior: worker checks every 5 minutes via `HEALTH_CHECK_URL`, marks `alive`/`dead` + `latency_ms`, gateway only selects `alive`, and manual checks can be triggered via the "Check now" button on the Dashboard or `POST /api/proxies/check-all`.

- [ ] **Step 3: Verify bat file parses correctly**

Run: `cmd.exe //c "start-dev.bat"` DO NOT run for real (will open multiple windows). Instead check syntax by reading the file again and ensuring each `start "..." cmd /k "..."` line is on a single line, not broken midway.

- [ ] **Step 4: Commit**

```bash
git add start-dev.bat README.md
git commit -m "chore: launch Celery worker and beat from start-dev.bat; update README"
```

---

### Task 8: Manual end-to-end verification

**Files:** No code modifications (run and observe only).

**Interfaces:**
- Consumes: All preceding tasks; Redis running locally.

- [ ] **Step 1: Ensure Redis is running**

Run: `venv\Scripts\python.exe -c "import redis; r = redis.Redis(); r.ping(); print('Redis OK')"`
Expected: `Redis OK`. If connection error → notify user to start Redis and pause this task.

- [ ] **Step 2: Run all tests**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: All PASS.

Run: `cd frontend && npm run build && npm run test`
Expected: Build OK, 3 tests PASS.

- [ ] **Step 3: Smoke test worker directly (without beat)**

Run task `check_all_proxies` synchronously in Python to verify worker can be imported and DB updates:

Run:
```bash
venv\Scripts\python.exe -c "from app.worker import check_all_proxies; print('dispatched:', check_all_proxies())"
```
Expected: Prints number of http/https proxies in DB (can be 0 if DB is empty — no error). If DB has proxies, check that status is updated:
```bash
venv\Scripts\python.exe -c "from sqlmodel import Session, select; from app.core.database import engine; from app.models.proxy import Proxy; s = Session(engine); [print(p.host, p.status, p.latency_ms) for p in s.exec(select(Proxy)).all()]"
```

Note: Running the task function directly (not via `.delay()`) does not require a broker — this step verifies DB + httpx logic is functional. The actual `.delay()` step requires running workers; let the user run `start-dev.bat` to observe.

- [ ] **Step 4: Report results to user**

Summary: What was completed, how to run (`start-dev.bat` now opens 2 additional Celery windows), and remind user to push when satisfied. DO NOT create extra commits, DO NOT push.

---

## Self-Review Notes

- **Spec coverage:** config (3.1) → Task 1; health service (3.2) → Task 2; worker (3.3) → Task 3; gateway alive-only (3.5) → Task 4; API trigger (3.4) → Task 5; frontend (3.6) → Task 6; operations (3.7) → Task 7; testing (section 5) → covered in Tasks 1-6; error handling (section 4) → implemented in Tasks 2/3.
- **Type consistency:** `CheckResult(alive, latency_ms)` used consistently across Tasks 2/3; `check_all_proxies` returns int, `check_proxy_task` returns str; endpoint returns `{detail, task_id}` matching frontend `CheckAllResponse`.
- **Addressed risks:** route `/check-all` placed before `/{proxy_id}`; engine indirection `_get_engine()` for tests; `.bat` CRLF verified; legacy `unknown`-included test flipped to excluded.
