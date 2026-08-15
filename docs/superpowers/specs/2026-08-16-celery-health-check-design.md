# ProxyHub — Phần 2: Celery Health Check Tự động (Design Spec)

- **Ngày:** 2026-08-16
- **Trạng thái:** Đã phê duyệt
- **Phạm vi:** Phần 2 trong 6 phần của roadmap (MVP, Health Check, Multi-tenant, Sticky Session, WebSocket Logs, Docker Compose)

## 1. Mục tiêu

Tự động kiểm tra sức khoẻ toàn bộ pool proxy theo chu kỳ bằng Celery + Redis:

- Celery Beat kích hoạt mỗi **5 phút** → worker kiểm tra từng proxy qua HTTP request.
- Mỗi proxy được cập nhật `status` (`alive`/`dead`), `latency_ms`, `last_checked_at`.
- Dashboard có nút **"Kiểm tra ngay"** để trigger thủ công (không cần chờ hết chu kỳ).
- Gateway chỉ còn chọn proxy `alive` (đúng cam kết trong spec MVP: "Sang Phần 2, gateway chỉ chọn `alive`").

### Quyết định nền tảng

| Quyết định | Lựa chọn |
|---|---|
| Task queue | Celery ≥ 5.4, broker/result backend là Redis (đã cài sẵn trên máy dev) |
| Lịch chạy | Celery Beat, 300 giây/lần (5 phút) |
| Fan-out | Task `check_all_proxies` đọc DB → dispatch mỗi proxy một task `check_proxy` |
| Target check | Env var `HEALTH_CHECK_URL`, mặc định `https://api.ipify.org` |
| Timeout | Env var `HEALTH_CHECK_TIMEOUT`, mặc định 10 giây |
| Scheme được check | Chỉ `http`/`https` (gateway chỉ dùng 2 scheme này); `socks5` giữ `unknown` |
| Windows | Worker/beat chạy với `--pool=solo` (Celery không hỗ trợ chính thức Windows) |

## 2. Kiến trúc

```
┌─────────────┐  mỗi 5 phút   ┌──────────────────────┐
│ Celery Beat │ ─────────────▶ │ check_all_proxies()  │  (task)
└─────────────┘                └──────────┬───────────┘
                                          │ đọc DB, fan-out
                                          ▼
┌─────────────────────────────┐   ┌──────────────────────┐
│ Dashboard                   │   │ check_proxy(id) × N  │  (task)
│ POST /api/proxies/check-all │──▶│                      │
│ (JWT, trả 202)              │   └──────────┬───────────┘
└─────────────────────────────┘              │ httpx GET HEALTH_CHECK_URL
                                             │ qua proxy (timeout 10s)
                                             ▼
                              ┌──────────────────────────────┐
                              │ SQLite: status, latency_ms,  │
                              │ last_checked_at, updated_at  │
                              └──────────────────────────────┘
```

### Luồng dữ liệu

1. **Beat** gọi `check_all_proxies` theo schedule.
2. `check_all_proxies` mở session, lấy toàn bộ proxy có scheme `http`/`https`, dispatch `check_proxy(proxy_id)` cho từng proxy, trả về số task đã dispatch.
3. `check_proxy(proxy_id)` mở session riêng, gọi `health_service.check_proxy()`:
   - HTTP request thành công (bất kỳ status code nào có response) → `status=alive`, `latency_ms` = thời gian request, `last_checked_at` = now.
   - Timeout / lỗi kết nối / không có response → `status=dead`, `latency_ms=None`, `last_checked_at` = now.
4. Commit từng proxy độc lập — một proxy lỗi không ảnh hưởng proxy khác.

## 3. Thay đổi chi tiết

### 3.1 Config — `app/core/config.py`

Thêm 4 field vào `Settings` (giữ `extra: "ignore"`):

| Field | Kiểu | Mặc định |
|---|---|---|
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/2` |
| `HEALTH_CHECK_URL` | `str` | `https://api.ipify.org` |
| `HEALTH_CHECK_TIMEOUT` | `float` | `10.0` |

`.env.example` đã có sẵn `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`; bổ sung `HEALTH_CHECK_URL` và `HEALTH_CHECK_TIMEOUT`.

### 3.2 Health service — `app/services/health_service.py` (mới)

Logic kiểm tra thuần, đồng bộ, **không phụ thuộc Celery** (để test được bằng pytest thường):

```python
@dataclass
class CheckResult:
    alive: bool
    latency_ms: float | None

def check_proxy(proxy: Proxy) -> CheckResult:
    """GET HEALTH_CHECK_URL qua proxy bằng httpx, timeout HEALTH_CHECK_TIMEOUT.
    Có response HTTP → alive; timeout/lỗi kết nối → dead."""
```

- Dùng `httpx.Client(proxy=...)` với URL dạng `{scheme}://{user}:{pass}@{host}:{port}` (chỉ thêm credentials khi có).
- Bắt mọi exception của httpx → `CheckResult(alive=False, latency_ms=None)`.
- Đo latency bằng `time.perf_counter()` quanh request.

### 3.3 Celery worker — `app/worker.py` (mới)

```python
celery_app = Celery("proxyhub", broker=..., backend=...)
celery_app.conf.beat_schedule = {
    "check-all-proxies-every-5-min": {
        "task": "app.worker.check_all_proxies",
        "schedule": 300.0,
    }
}
```

- `check_all_proxies`: đọc DB (session riêng), filter scheme ∈ {http, https}, dispatch `check_proxy.delay(proxy_id)` từng cái, return số lượng.
- `check_proxy(proxy_id)`: đọc proxy theo id (không thấy → log warning, return), gọi `health_service.check_proxy`, cập nhật 4 field (`status`, `latency_ms`, `last_checked_at`, `updated_at`), commit.
- Mỗi task tự tạo `Session(engine)` — không dùng FastAPI dependency.

### 3.4 API trigger — `app/api/proxies.py`

```
POST /api/proxies/check-all   (yêu cầu JWT như các endpoint khác)
→ dispatch check_all_proxies.delay()
→ 202 Accepted, body {"detail": "Health check started", "task_id": "..."}
```

Import task từ `app.worker` (lazy, tránh import Celery khi chưa cần — nhưng vì worker.py chỉ tạo Celery app, import thẳng là an toàn).

### 3.5 Gateway chỉ chọn proxy alive — `app/services/proxy_service.py`

`select_random_proxy`: đổi điều kiện từ `Proxy.status != ProxyStatus.DEAD` thành `Proxy.status == ProxyStatus.ALIVE`. Đây là thay đổi hành vi đã cam kết trong spec MVP.

### 3.6 Frontend — nút "Kiểm tra ngay"

- `frontend/src/api/proxies.ts`: thêm `triggerCheckAll()` → `POST /api/proxies/check-all`.
- `frontend/src/pages/ProxiesPage.tsx`: thêm Button "Kiểm tra ngay" (icon `RefreshCw`) cạnh các nút Import/Add trên toolbar. Bấm → gọi API → toast success "Đã gửi yêu cầu kiểm tra sức khoẻ" (hoặc toast error nếu API lỗi). Không tự động refetch — user bấm refresh bảng như thường.

### 3.7 Vận hành

- `requirements.txt`: thêm `celery>=5.4.0`, `redis>=5.0.0`.
- `start-dev.bat`: thêm 2 khối — Celery Worker (`celery -A app.worker.celery_app worker --loglevel=info --pool=solo`) và Celery Beat (`celery -A app.worker.celery_app beat --loglevel=info`), dùng venv như các khối khác.
- README: cập nhật checklist `[x] Celery Health Check tự động`, bổ sung `HEALTH_CHECK_URL`/`HEALTH_CHECK_TIMEOUT` vào phần `.env`.

## 4. Error handling

| Tình huống | Xử lý |
|---|---|
| Proxy timeout / từ chối kết nối | Đánh dấu `dead`, ghi `last_checked_at`, không retry trong chu kỳ đó |
| Proxy bị xoá giữa lúc dispatch và check | `check_proxy` không tìm thấy id → log warning, bỏ qua |
| Một task crash | Chỉ task đó fail (Celery mặc định); các proxy khác vẫn được check |
| SQLite lock khi API + worker ghi đồng thời | Đã có WAL + `busy_timeout=5000ms` từ Phần 1 |
| Redis chưa chạy | Worker/beat không start được — báo lỗi rõ trong terminal (không xử lý thêm) |
| Proxy scheme `socks5` | Bỏ qua trong health check (giữ `unknown`), không được gateway chọn vì không còn `alive` |

## 5. Testing

- **Unit `health_service`** (mock httpx): response thành công → alive + latency; timeout → dead; lỗi kết nối → dead; proxy có credentials → URL proxy chứa credentials.
- **Unit `proxy_service`**: `select_random_proxy` chỉ trả proxy `alive` (không trả `unknown`/`dead`).
- **API `POST /api/proxies/check-all`**: mock `check_all_proxies.delay()` → 202 + task_id; không có JWT → 401.
- **Worker tasks**: test `check_all_proxies` dispatch đúng N task (mock `.delay`), `check_proxy` cập nhật đúng field (dùng DB test, mock `health_service`).
- Frontend: giữ 3 test hiện có pass; build sạch.

## 6. Ngoài phạm vi

- Health check cho `socks5` (cần `socksio`; để phần sau nếu cần).
- Retry/backoff khi proxy dead, xoá tự động proxy dead.
- Trang Settings để chỉnh `HEALTH_CHECK_URL` từ UI.
- Realtime cập nhật kết quả lên Dashboard (WebSocket — Phần 5).
- Chạy Celery qua Docker/WSL2 (Phần 6 — Docker Compose).
