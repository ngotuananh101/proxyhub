# Celery Health Check (Phần 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tự động kiểm tra sức khoẻ pool proxy mỗi 5 phút bằng Celery + Redis, cập nhật `status`/`latency_ms`/`last_checked_at`, thêm nút "Kiểm tra ngay" trên Dashboard, và gateway chỉ chọn proxy `alive`.

**Architecture:** Celery Beat gọi task `check_all_proxies` mỗi 300s → fan-out mỗi proxy một task `check_proxy` → gọi `health_service.check_proxy()` (httpx GET qua proxy) → ghi kết quả vào SQLite. Endpoint `POST /api/proxies/check-all` (JWT) dispatch cùng task để trigger thủ công.

**Tech Stack:** Celery ≥5.4, redis-py ≥5.0, httpx (đã có), SQLModel, FastAPI, React + TanStack Query + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-08-16-celery-health-check-design.md`

## Global Constraints

- Chạy trên **Windows native**: Celery worker/beat phải chạy với `--pool=solo`; mọi file `.bat` phải có line ending **CRLF**.
- Không bao giờ in giá trị secret từ `.env` (SECRET_KEY, INTERNAL_API_KEY) ra output/log.
- Dev services bind `127.0.0.1`.
- Backend chạy bằng venv: `venv\Scripts\python.exe`; test backend: `venv\Scripts\python.exe -m pytest`.
- Frontend: `cd frontend && npm run ...`; shadcn base là **Base UI** (dùng prop `render`, KHÔNG dùng `asChild`; icon trong Button dùng `data-icon="inline-start|inline-end"`, không thêm class size; toast dùng `toast.add({ type, title, description })`).
- Commit message tiếng Anh, conventional commits (`feat:`, `test:`, `chore:`, `docs:`). KHÔNG `git push` — user tự push.
- Test backend hiện có: 59 passed trước khi bắt đầu. Test frontend: 3 passed (`npm run test` chạy vitest).
- Proxy scheme `socks5` KHÔNG được health check (giữ `unknown`).
- `select_random_proxy` sau Phần 2 chỉ trả proxy `alive` (thay đổi hành vi đã cam kết trong spec MVP).

---

### Task 1: Config + dependencies (Celery, Redis, health check settings)

**Files:**
- Modify: `app/core/config.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: không có (task đầu tiên).
- Produces: `settings.CELERY_BROKER_URL`, `settings.CELERY_RESULT_BACKEND`, `settings.HEALTH_CHECK_URL`, `settings.HEALTH_CHECK_TIMEOUT` — các task sau đọc 4 field này.

- [ ] **Step 1: Đọc file test config hiện có**

Đọc `tests/test_config.py` để biết pattern test Settings đang dùng (fixture, monkeypatch env, …). Viết test mới theo đúng pattern đó.

- [ ] **Step 2: Viết test failing cho 4 field mới**

Thêm vào `tests/test_config.py` (giữ nguyên các test cũ):

```python
def test_celery_and_health_check_defaults(monkeypatch):
    # Xoá env để ăn default
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

Lưu ý: nếu test hiện có trong file dùng cách khởi tạo `Settings` khác (ví dụ không truyền `_env_file=None`), điều chỉnh cho khớp pattern — mục tiêu là assert 4 giá trị mặc định.

- [ ] **Step 3: Chạy test để chắc chắn FAIL**

Run: `venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: test mới FAIL (field chưa tồn tại — `AttributeError` hoặc assert sai).

- [ ] **Step 4: Thêm 4 field vào Settings**

Sửa `app/core/config.py` — thêm 4 dòng vào class `Settings` (sau `CORS_ORIGINS`):

```python
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    HEALTH_CHECK_URL: str = "https://api.ipify.org"
    HEALTH_CHECK_TIMEOUT: float = 10.0
```

- [ ] **Step 5: Thêm dependencies vào requirements.txt**

Thêm 2 dòng vào cuối `requirements.txt`:

```
celery>=5.4.0
redis>=5.0.0
```

Cài đặt:

Run: `venv\Scripts\pip.exe install -r requirements.txt`
Expected: cài thành công celery + redis (và các dependency con).

- [ ] **Step 6: Cập nhật .env.example**

Trong `.env.example`, thêm 2 dòng vào block `# Celery (Phần 2)` (sau `CELERY_RESULT_BACKEND`):

```
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=10
```

- [ ] **Step 7: Chạy test để chắc chắn PASS**

Run: `venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: tất cả PASS.

- [ ] **Step 8: Commit**

```bash
git add app/core/config.py requirements.txt .env.example tests/test_config.py
git commit -m "feat: add Celery and health check settings with dependencies"
```

---

### Task 2: Health service — logic kiểm tra proxy thuần (httpx)

**Files:**
- Create: `app/services/health_service.py`
- Test: `tests/test_health_service.py`

**Interfaces:**
- Consumes: `settings.HEALTH_CHECK_URL`, `settings.HEALTH_CHECK_TIMEOUT` (Task 1); `Proxy` model (`app/models/proxy.py`) với các field `scheme`, `host`, `port`, `username`, `password`.
- Produces:
  - `CheckResult` dataclass: `alive: bool`, `latency_ms: float | None`.
  - `check_proxy(proxy: Proxy) -> CheckResult` — hàm đồng bộ, KHÔNG phụ thuộc Celery/DB session.
  - `build_proxy_url(proxy: Proxy) -> str` — helper dựng URL proxy (được export để test).

- [ ] **Step 1: Viết test failing**

Tạo `tests/test_health_service.py`:

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
        # Proxy hoạt động = có response HTTP, kể cả 403/500 từ target
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

- [ ] **Step 2: Chạy test để chắc chắn FAIL**

Run: `venv\Scripts\python.exe -m pytest tests/test_health_service.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.services.health_service'`.

- [ ] **Step 3: Viết implementation**

Tạo `app/services/health_service.py`:

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
    """GET HEALTH_CHECK_URL qua proxy. Có response HTTP -> alive; lỗi/timeout -> dead."""
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

- [ ] **Step 4: Chạy test để chắc chắn PASS**

Run: `venv\Scripts\python.exe -m pytest tests/test_health_service.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/health_service.py tests/test_health_service.py
git commit -m "feat: add health service checking proxies via httpx"
```

---

### Task 3: Celery worker — `app/worker.py` với 2 task + beat schedule

**Files:**
- Create: `app/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `settings.CELERY_BROKER_URL`, `settings.CELERY_RESULT_BACKEND` (Task 1); `health_service.check_proxy` (Task 2); `engine` từ `app.core.database`; `Proxy`, `ProxyStatus` từ `app.models.proxy`.
- Produces:
  - `celery_app` — Celery instance tên `"proxyhub"`, `beat_schedule` key `"check-all-proxies-every-5-min"` chạy task `"app.worker.check_all_proxies"` mỗi `300.0` giây.
  - Task `check_all_proxies()` → trả `int` (số task đã dispatch).
  - Task `check_proxy_task(proxy_id: int)` → trả `str` (`"alive"`, `"dead"`, hoặc `"not_found"`). Tên Celery task là `app.worker.check_proxy_task`.

- [ ] **Step 1: Viết test failing**

Tạo `tests/test_worker.py`:

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
        assert count == 2  # socks5 bị bỏ qua
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

**Quan trọng — DB trong test:** các task trong `app/worker.py` dùng `engine` import từ `app.core.database`. Fixture `engine` của conftest tạo engine in-memory riêng. Để test chạy đúng engine fixture, task phải lấy engine qua một hàm có thể patch, hoặc worker phải dùng `Session(engine)` với engine import từ `app.core.database` và test patch `app.worker.engine`. Cách đơn giản nhất: trong `app/worker.py` viết `from app.core import database` rồi dùng `database.engine` — trong test, monkeypatch `app.worker.database.engine = engine_fixture` KHÔNG hoạt động vì `database` là module thật. Vì vậy dùng pattern: khai báo hàm helper `_get_engine()` trong worker trả về `database.engine`, và test patch `app.worker._get_engine` trả về fixture engine. Chi tiết ở Step 3.

- [ ] **Step 2: Chạy test để chắc chắn FAIL**

Run: `venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.worker'`.

- [ ] **Step 3: Viết implementation**

Tạo `app/worker.py`:

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
    """Indirection để test có thể thay engine bằng DB in-memory."""
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

Thêm vào cuối `tests/conftest.py` fixture autouse để mọi test trong `app.worker` dùng engine in-memory:

```python
@pytest.fixture(autouse=True)
def _patch_worker_engine(engine, monkeypatch):
    """Nếu app.worker đã được import, trỏ engine của nó về DB test."""
    import sys

    if "app.worker" in sys.modules:
        import app.worker

        monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)
```

Lưu ý: fixture này phụ thuộc fixture `engine` nên mọi test đều tạo engine in-memory — điều này đã đúng với mọi test hiện có (chúng đều dùng `engine` hoặc `session`).

- [ ] **Step 4: Chạy test để chắc chắn PASS**

Run: `venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Chạy toàn bộ suite backend để chắc chắn không vỡ gì**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: tất cả PASS (59 cũ + test mới).

- [ ] **Step 6: Commit**

```bash
git add app/worker.py tests/test_worker.py tests/conftest.py
git commit -m "feat: add Celery worker with health check tasks and beat schedule"
```

---

### Task 4: Gateway chỉ chọn proxy alive

**Files:**
- Modify: `app/services/proxy_service.py`
- Test: `tests/test_proxy_service.py`

**Interfaces:**
- Consumes: `ProxyStatus` từ `app.models.proxy`.
- Produces: `select_random_proxy(session)` chỉ trả proxy có `status == ALIVE` và scheme ∈ {http, https}; trả `None` nếu không có.

- [ ] **Step 1: Sửa test theo hành vi mới**

Trong `tests/test_proxy_service.py`, class `TestSelectRandomProxy`:

Thay test `test_select_includes_unknown` bằng:

```python
    def test_select_excludes_unknown(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is None
```

Giữ nguyên `test_select_excludes_dead`, `test_select_excludes_socks5`, `test_select_empty_pool` (chúng vẫn đúng với hành vi mới).

- [ ] **Step 2: Chạy test để chắc chắn FAIL**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxy_service.py -v`
Expected: `test_select_excludes_unknown` FAIL (hiện tại unknown vẫn được chọn).

- [ ] **Step 3: Đổi điều kiện trong select_random_proxy**

Trong `app/services/proxy_service.py`, sửa `select_random_proxy`:

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

(Chỉ đổi dòng `Proxy.status != ProxyStatus.DEAD` thành `Proxy.status == ProxyStatus.ALIVE`.)

- [ ] **Step 4: Chạy test để chắc chắn PASS**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxy_service.py tests/test_internal_api.py tests/test_gateway_plugin.py -v`
Expected: tất cả PASS. Nếu `test_internal_api.py` hoặc `test_gateway_plugin.py` có test seed proxy `unknown`/`dead` rồi expect chọn được, phải cập nhật seed thành `status=ProxyStatus.ALIVE` cho khớp hành vi mới.

- [ ] **Step 5: Chạy toàn bộ suite backend**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/proxy_service.py tests/test_proxy_service.py tests/test_internal_api.py tests/test_gateway_plugin.py
git commit -m "feat: gateway selects only alive proxies"
```

(Lượt bỏ khỏi `git add` các file test không cần sửa.)

---

### Task 5: API endpoint `POST /api/proxies/check-all`

**Files:**
- Modify: `app/api/proxies.py`
- Test: `tests/test_proxies_api.py`

**Interfaces:**
- Consumes: task `check_all_proxies` từ `app.worker` (Task 3); `get_current_user` từ `app.api.deps`.
- Produces: `POST /api/proxies/check-all` — yêu cầu JWT; dispatch `check_all_proxies.delay()`; trả **202** với body `{"detail": "Health check started", "task_id": "<id>"}`.

- [ ] **Step 1: Viết test failing**

Thêm vào `tests/test_proxies_api.py`:

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

Thêm import đầu file: `from unittest.mock import patch`.

- [ ] **Step 2: Chạy test để chắc chắn FAIL**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxies_api.py -v`
Expected: 2 test mới FAIL (404 hoặc 405 — endpoint chưa tồn tại).

- [ ] **Step 3: Thêm endpoint**

Trong `app/api/proxies.py`:

Thêm import đầu file:

```python
from app.worker import check_all_proxies
```

Thêm endpoint (đặt TRƯỚC `@router.get("/{proxy_id}")` để tránh route `check-all` bị bắt bởi `{proxy_id}`):

```python
@router.post("/check-all", status_code=status.HTTP_202_ACCEPTED)
def trigger_check_all(_: User = Depends(get_current_user)):
    result = check_all_proxies.delay()
    return {"detail": "Health check started", "task_id": result.id}
```

- [ ] **Step 4: Chạy test để chắc chắn PASS**

Run: `venv\Scripts\python.exe -m pytest tests/test_proxies_api.py -v`
Expected: tất cả PASS.

- [ ] **Step 5: Chạy toàn bộ suite backend**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/proxies.py tests/test_proxies_api.py
git commit -m "feat: add POST /api/proxies/check-all to trigger health check"
```

---

### Task 6: Frontend — nút "Kiểm tra ngay" trên trang Proxies

**Files:**
- Modify: `frontend/src/api/proxies.ts`
- Modify: `frontend/src/pages/ProxiesPage.tsx`

**Interfaces:**
- Consumes: `POST /api/proxies/check-all` (Task 5) trả 202 + `{detail, task_id}`; axios client từ `./client`; toast từ `@/components/ui/toast`.
- Produces: `triggerCheckAll(): Promise<{ detail: string; task_id: string }>` trong `frontend/src/api/proxies.ts`.

- [ ] **Step 1: Thêm API function**

Trong `frontend/src/api/proxies.ts`, thêm sau `fetchStats`:

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

- [ ] **Step 2: Thêm nút vào ProxiesPage**

Trong `frontend/src/pages/ProxiesPage.tsx`:

Thêm import:

```typescript
import { RefreshCwIcon } from 'lucide-react'
import { triggerCheckAll } from '@/api/proxies'  // gộp vào import sẵn có từ '@/api/proxies'
```

Thêm state và handler trong component (cạnh các state khác):

```typescript
const [checking, setChecking] = useState(false)

const handleCheckAll = async () => {
  setChecking(true)
  try {
    await triggerCheckAll()
    toast.add({
      type: 'success',
      title: 'Đã gửi yêu cầu kiểm tra sức khoẻ',
      description: 'Kết quả sẽ cập nhật sau vài phút.',
    })
  } catch {
    toast.add({
      type: 'error',
      title: 'Không thể gửi yêu cầu kiểm tra',
    })
  } finally {
    setChecking(false)
  }
}
```

Thêm nút vào khối toolbar `<div className="flex gap-2">` (đặt TRƯỚC nút "Add Proxy"):

```tsx
<Button variant="outline" onClick={handleCheckAll} disabled={checking}>
  <RefreshCwIcon data-icon="inline-start" />
  Kiểm tra ngay
</Button>
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TypeScript.

- [ ] **Step 4: Chạy test frontend**

Run: `cd frontend && npm run test`
Expected: 3 tests PASS (không thêm test mới cho nút — giữ phạm vi gọn; nếu muốn có thể thêm test render nút nhưng không bắt buộc).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/proxies.ts frontend/src/pages/ProxiesPage.tsx
git commit -m "feat: add health check trigger button to proxies page"
```

---

### Task 7: Vận hành — start-dev.bat, README, .env.example

**Files:**
- Modify: `start-dev.bat`
- Modify: `README.md`

**Interfaces:**
- Consumes: `app.worker.celery_app` (Task 3); các env var Celery (Task 1).
- Produces: `start-dev.bat` khởi động thêm Celery Worker + Beat; README phản ánh Phần 2 hoàn thành.

- [ ] **Step 1: Thêm 2 khối Celery vào start-dev.bat**

Trong `start-dev.bat`, sau khối Gateway (dòng `start "ProxyHub Gateway" ...`), thêm:

```bat
REM --- 4. Celery Worker: health check tasks (Windows can --pool=solo) ---
start "ProxyHub Celery Worker" cmd /k "venv\Scripts\celery.exe -A app.worker.celery_app worker --loglevel=info --pool=solo"

REM --- 5. Celery Beat: scheduler 5 phut/lan ---
start "ProxyHub Celery Beat" cmd /k "venv\Scripts\celery.exe -A app.worker.celery_app beat --loglevel=info"
```

Cập nhật dòng tiêu đề đầu script cho phản ánh đủ thành phần:

```bat
echo   ProxyHub - Khoi dong Backend + Frontend + Gateway + Celery
```

Và thêm 2 dòng vào khối echo tổng kết cuối script:

```bat
echo   Celery  : worker + beat (health check moi 5 phut)
```

**Quan trọng:** file `.bat` phải giữ line ending **CRLF**. Sau khi sửa, kiểm tra:

Run: `file start-dev.bat`
Expected: chứa `CRLF` (ví dụ `with CRLF line terminators`). Nếu ra `LF` hoặc không có CRLF, convert lại: `awk 'sub(/$/, "\r")' start-dev.bat > tmp && mv tmp start-dev.bat`.

- [ ] **Step 2: Cập nhật README**

Trong `README.md`:

1. Đổi dòng `- [ ] Celery Health Check tự động` thành `- [x] Celery Health Check tự động`.
2. Trong phần `.env` (quanh dòng 226-235), thêm 2 dòng vào block Celery nếu chưa có:

```
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=10
```

3. Trong phần `### 3. Health Check` (quanh dòng 278), đảm bảo mô tả khớp hành vi mới: worker check mỗi 5 phút qua `HEALTH_CHECK_URL`, đánh dấu `alive`/`dead` + `latency_ms`, gateway chỉ chọn `alive`, và có thể trigger thủ công bằng nút "Kiểm tra ngay" trên Dashboard hoặc `POST /api/proxies/check-all`.

- [ ] **Step 3: Kiểm tra bat file parse được**

Run: `cmd.exe //c "start-dev.bat"` KHÔNG được chạy thật (sẽ mở nhiều cửa sổ). Thay vào đó kiểm tra cú pháp bằng cách đọc lại file và chắc chắn mỗi dòng `start "..." cmd /k "..."` nằm trên một dòng duy nhất, không xuống dòng giữa chừng.

- [ ] **Step 4: Commit**

```bash
git add start-dev.bat README.md
git commit -m "chore: launch Celery worker and beat from start-dev.bat; update README"
```

---

### Task 8: Kiểm chứng end-to-end thủ công

**Files:** không sửa code (chỉ chạy và quan sát).

**Interfaces:**
- Consumes: toàn bộ các task trên; Redis đang chạy trên máy.

- [ ] **Step 1: Chắc chắn Redis đang chạy**

Run: `venv\Scripts\python.exe -c "import redis; r = redis.Redis(); r.ping(); print('Redis OK')"`
Expected: `Redis OK`. Nếu lỗi kết nối → báo user khởi động Redis rồi dừng task này.

- [ ] **Step 2: Chạy toàn bộ test**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: tất cả PASS.

Run: `cd frontend && npm run build && npm run test`
Expected: build OK, 3 tests PASS.

- [ ] **Step 3: Smoke test worker trực tiếp (không cần beat)**

Chạy task `check_all_proxies` synchronously trong Python để xác nhận worker import được và DB cập nhật:

Run:
```bash
venv\Scripts\python.exe -c "from app.worker import check_all_proxies; print('dispatched:', check_all_proxies())"
```
Expected: in ra số proxy http/https trong DB (có thể là 0 nếu DB trống — không lỗi). Nếu DB có proxy, kiểm tra status được cập nhật:
```bash
venv\Scripts\python.exe -c "from sqlmodel import Session, select; from app.core.database import engine; from app.models.proxy import Proxy; s = Session(engine); [print(p.host, p.status, p.latency_ms) for p in s.exec(select(Proxy)).all()]"
```

Lưu ý: chạy trực tiếp hàm task (không qua `.delay()`) không cần broker — bước này xác nhận logic DB + httpx hoạt động. Bước `.delay()` thật cần worker chạy; để user tự chạy `start-dev.bat` và quan sát.

- [ ] **Step 4: Báo cáo kết quả cho user**

Tổng kết: những gì đã làm, cách chạy (`start-dev.bat` giờ mở thêm 2 cửa sổ Celery), và nhắc user tự push khi hài lòng. KHÔNG tự commit thêm, KHÔNG push.

---

## Self-Review Notes

- **Spec coverage:** config (3.1) → Task 1; health service (3.2) → Task 2; worker (3.3) → Task 3; gateway alive-only (3.5) → Task 4; API trigger (3.4) → Task 5; frontend (3.6) → Task 6; vận hành (3.7) → Task 7; testing (mục 5) → phủ trong Task 1-6; error handling (mục 4) → nằm trong implementation của Task 2/3.
- **Type consistency:** `CheckResult(alive, latency_ms)` dùng thống nhất Task 2/3; `check_all_proxies` trả int, `check_proxy_task` trả str; endpoint trả `{detail, task_id}` khớp frontend `CheckAllResponse`.
- **Rủi ro đã xử lý:** route `/check-all` đặt trước `/{proxy_id}`; engine indirection `_get_engine()` cho test; `.bat` CRLF được kiểm tra; test `unknown`-included cũ được lật thành excluded.
