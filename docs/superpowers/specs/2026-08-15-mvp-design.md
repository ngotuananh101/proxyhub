# ProxyHub — Phần 1: MVP End-to-End (Design Spec)

- **Ngày:** 2026-08-15
- **Trạng thái:** Đã phê duyệt
- **Phạm vi:** Phần 1 trong 6 phần của roadmap (MVP, Health Check, Multi-tenant, Sticky Session, WebSocket Logs, Docker Compose)

## 1. Mục tiêu

Chạy được luồng end-to-end trên Windows native:

```
curl -x http://127.0.0.1:8899 http://target
```

→ request đi ra internet qua một proxy trong pool, tự xoay IP giữa các request, quản lý pool bằng Dashboard React có đăng nhập JWT.

### Quyết định nền tảng (áp dụng cho toàn dự án)

| Quyết định | Lựa chọn |
|---|---|
| Phạm vi MVP | Full-stack end-to-end (Backend + Gateway + Dashboard) |
| Auth | JWT ngay từ MVP, tạo user qua CLI (không có register công khai) |
| Kiểm thử | pytest (backend) + Vitest/Testing Library (frontend) |
| Môi trường dev | Windows native: Redis qua Memurai/Redis-Windows, Celery `--pool=solo` |
| Gateway lấy proxy | Gọi internal API mỗi request (không cache tại plugin) |

## 2. Kiến trúc Backend

```
app/
├── main.py              # FastAPI app, mount routers, tạo bảng khi khởi động
├── cli.py               # CLI: create-admin (argparse, không thêm dependency)
├── core/
│   ├── config.py        # pydantic-settings đọc .env
│   ├── database.py      # SQLModel engine, SQLite WAL + busy_timeout=5000ms
│   └── security.py      # JWT encode/decode, hash password (bcrypt trực tiếp)
├── models/              # SQLModel bảng: User, Proxy
├── schemas/             # Pydantic request/response
├── api/
│   ├── deps.py          # get_current_user (JWT), verify_internal_key
│   ├── auth.py          # /api/auth/*
│   ├── proxies.py       # /api/proxies/*
│   ├── stats.py         # /api/stats/summary
│   └── internal.py      # /internal/proxies (X-Internal-Key)
├── services/
│   ├── proxy_service.py # parse/validate/import text, dedupe, chọn proxy
│   └── auth_service.py  # login, tạo user
└── gateway/
    └── plugin.py        # RotateProxyPlugin (chạy tiến trình riêng)
```

- Không dùng Alembic ở MVP: SQLModel `create_all()` khi khởi động. Migration thêm khi schema phức tạp hơn (Phần 3).
- Ruff làm linter/formatter duy nhất cho Python.
- Hash password bằng `bcrypt` trực tiếp (không dùng `passlib` — passlib có bug đã biết với bcrypt ≥ 4.1).

## 3. Data Model

### User

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | int PK | |
| username | str unique | |
| email | str unique, nullable | |
| hashed_password | str | bcrypt |
| is_admin | bool | mặc định `false` |
| created_at | datetime | |

### Proxy

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | int PK | |
| scheme | str | `http` / `https` (MVP — socks5 lưu được nhưng gateway không dùng) |
| host | str | |
| port | int | |
| username / password | str nullable | credential upstream |
| status | enum | `unknown` / `alive` / `dead`, mặc định `unknown` |
| latency_ms | float nullable | để trống cho Phần 2 |
| last_checked_at | datetime nullable | để trống cho Phần 2 |
| created_at / updated_at | datetime | |

- Unique constraint: `(scheme, host, port)` để dedupe khi import.
- `status` mặc định `unknown` vì MVP chưa có health check. Gateway chọn proxy `status != 'dead'` (chấp nhận `unknown` lẫn `alive`). Sang Phần 2, gateway chỉ chọn `alive`.

## 4. API Design

### Auth — `/api/auth`

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/auth/login` | Body `{username, password}` → `{access_token, token_type: "bearer"}` |
| GET | `/api/auth/me` | Thông tin user hiện tại (cần JWT) |

- JWT payload: `sub` (user id), `exp`. Thời hạn theo `ACCESS_TOKEN_EXPIRE_MINUTES` (mặc định 1440).
- Không có endpoint register công khai — user chỉ tạo qua CLI `create-admin`. Register để Phần 3.

### Proxies — `/api/proxies` (cần JWT)

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/proxies` | List + phân trang (`?page=1&size=20`), filter `?status=&scheme=&q=` |
| POST | `/api/proxies` | Thêm 1 proxy (body JSON) |
| POST | `/api/proxies/import` | Body `{text}` — parse nhiều dòng → `{imported, duplicates, invalid: [{line, reason}]}` |
| GET | `/api/proxies/{id}` | Chi tiết 1 proxy |
| PUT | `/api/proxies/{id}` | Sửa host, port, credential |
| DELETE | `/api/proxies/{id}` | Xoá 1 proxy |
| DELETE | `/api/proxies` | Xoá nhiều: body `{ids: [...]}` |

### Stats — `/api/stats` (cần JWT)

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/stats/summary` | `{total, alive, dead, unknown}` |

### Internal — `/internal` (cần header `X-Internal-Key`)

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/internal/proxies?strategy=random` | Trả 1 proxy dùng được: `{id, scheme, host, port, username, password}` |

Chi tiết:

- Chọn proxy: query `status != 'dead'`, chọn ngẫu nhiên bằng Python `random.choice` (pool MVP nhỏ, không cần SQL random).
- `strategy`: mặc định `random`; MVP chỉ hỗ trợ `random`, giá trị khác → `400`. Giữ param để Phần 4 thêm `sticky` không vỡ API.
- Không có proxy dùng được → `404 {detail: "No available proxy"}`.
- Xác thực: so khớp `X-Internal-Key` với `INTERNAL_API_KEY` trong env (constant-time compare). Sai/thiếu → `401`.
- Chỉ trả field gateway cần để nối upstream, không lộ thông tin nội bộ khác.

### Quy ước chung

- Lỗi chuẩn FastAPI: `400` validate, `401` chưa xác thực, `404` không tìm thấy, `409` trùng proxy khi thêm đơn lẻ.
- Response schema tách riêng khỏi DB model (không lộ `hashed_password`).
- CORS: cho phép `http://localhost:5173`, config qua env `CORS_ORIGINS`.

## 5. Gateway Plugin (`RotateProxyPlugin`)

### Cách chạy

```bash
proxy --plugin-name app.gateway.plugin.RotateProxyPlugin \
      --hostname 127.0.0.1 --port 8899 --threaded
```

- Threaded mode để plugin gọi HTTP đồng bộ tới Backend không block event loop. Trade-off chấp nhận được ở quy mô MVP.
- Plugin đọc config từ env khi khởi động: `GATEWAY_API_URL`, `INTERNAL_API_KEY`.

### Luồng xử lý mỗi request

```
Client request → before_upstream_connection()
  ├─ GET {GATEWAY_API_URL}?strategy=random (timeout 2s, header X-Internal-Key)
  ├─ 200 → set request.upstream = http://[user:pass@]host:port → tiếp tục
  ├─ 404 (không có proxy) → log + teardown, trả 502 "No available proxy"
  └─ Lỗi/timeout (Backend down) → log + teardown, trả 502 "Proxy service unavailable"
```

- Hook `before_upstream_connection`: gọi API và gán upstream; trả `None` để từ chối request. Nếu cơ chế proxy.py không cho trả 502 đẹp, fallback là log + teardown (client nhận connection reset) — chấp nhận ở MVP, ghi chú lại.
- Proxy auth upstream: plugin set upstream URL kèm credential. Nếu proxy.py base plugin không tự inject `Proxy-Authorization`, plugin thêm header thủ công (cho cả HTTP thường lẫn CONNECT). Verify bằng test tích hợp khi implement.

### Nguyên tắc thiết kế

1. Plugin không giữ state — mỗi request một lần gọi API độc lập. Không cache, không retry tự động (request fail thì client tự retry, sẽ được IP khác — chính là "xoay proxy").
2. Không xác thực client ở MVP — gateway bind `127.0.0.1`. Proxy-auth per user để Phần 3.
3. Log tối thiểu: mỗi request 1 dòng (proxy được chọn, target host, kết quả) ra stdout bằng Python logging. Ghi log vào DB để Phần 5.
4. Không loop-prevention ở MVP (chặn request tới chính Backend) — việc của Phần 5/6.

## 6. Frontend (React Dashboard)

### Stack & cấu trúc

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts        # Axios: baseURL từ VITE_API_URL, gắn Authorization, 401 → redirect login
│   │   ├── auth.ts          # login(), me()
│   │   └── proxies.ts       # list/create/import/update/delete, stats
│   ├── components/
│   │   ├── ui/              # shadcn/ui
│   │   ├── ProxyTable.tsx   # Bảng proxy + filter + phân trang
│   │   ├── ImportDialog.tsx # Paste text import nhiều proxy
│   │   ├── ProxyForm.tsx    # Form thêm/sửa 1 proxy
│   │   └── StatCards.tsx    # Total/Alive/Dead/Unknown
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   └── ProxiesPage.tsx  # Trang chính duy nhất của MVP
│   ├── lib/auth.ts          # Token trong localStorage, hook useAuth
│   ├── App.tsx              # Router: /login, / (protected)
│   └── main.tsx
├── .env.example             # VITE_API_URL, VITE_WS_URL (để sẵn cho Phần 5)
└── package.json
```

### Màn hình

**Login (`/login`):** form username/password → `/api/auth/login` → lưu token localStorage → chuyển `/`. Đã có token hợp lệ thì vào thẳng `/`.

**Proxies (`/`):**

- Hàng StatCards trên cùng (gọi `/api/stats/summary`).
- Toolbar: ô tìm kiếm host, filter status (All/Alive/Dead/Unknown), nút Add Proxy / Import / Delete selected.
- ProxyTable: checkbox, scheme (badge), host:port, credential (ẩn, hiện khi bấm 👁), status (badge màu), latency (— ở MVP), created_at, hành động sửa/xoá. Phân trang 20 dòng/trang.
- ImportDialog: textarea paste nhiều dòng → `/api/proxies/import` → hiện `imported / duplicates / invalid` (kèm lý do từng dòng lỗi) → reload bảng.
- ProxyForm (dialog): scheme (chỉ http/https — socks5 disabled kèm tooltip "chưa hỗ trợ qua gateway"), host, port, username, password.

### Quy ước

- React Query (TanStack Query) cho data fetching — cache, loading/error, invalidate sau mutation.
- React Router v6, route `/` bọc trong guard kiểm tra token.
- Tailwind + shadcn/ui, dark mode mặc định.
- Không làm ở MVP: trang Settings (Phần 2), realtime logs (Phần 5), quản lý user/pool (Phần 3).

## 7. Scaffold & Dependencies

```
proxyhub/
├── app/                    # Backend
├── frontend/               # React
├── tests/                  # pytest: unit + integration backend
├── requirements.txt        # fastapi, uvicorn, sqlmodel, pydantic-settings,
│                           #   celery (cài sẵn cho Phần 2), proxy.py, bcrypt,
│                           #   PyJWT, httpx, python-multipart
├── requirements-dev.txt    # pytest, pytest-asyncio, ruff
├── .env.example            # Như README + INTERNAL_API_KEY + CORS_ORIGINS
├── .gitignore              # venv, .env, *.db, node_modules, dist
├── pyproject.toml          # ruff + pytest config
└── README.md, LICENSE      # Đã có
```

## 8. Chiến lược test

### Backend (pytest)

| Nhóm | Test gì |
|---|---|
| `proxy_service` | Parse text import: dòng hợp lệ, dòng lỗi (sai scheme, thiếu port, URL rác), dedupe, socks5 bị loại khỏi gateway selection |
| Auth | Login đúng/sai password, JWT hết hạn, endpoint không token → 401 |
| API proxies | CRUD đầy đủ, filter/phân trang, import trả đúng counts, xoá nhiều |
| Internal API | Không key → 401, sai key → 401, có key → trả proxy `unknown`/`alive`, không trả `dead`, hết proxy → 404 |
| Gateway plugin | Mock Backend: 200/404/timeout |
| Integration | Chạy uvicorn + gateway thật với DB temp, `curl -x` qua mock target server → assert IP đúng proxy |

### Frontend (Vitest + Testing Library)

- ProxyTable: render danh sách mock, filter theo status.
- ImportDialog: submit text → gọi đúng API, hiện kết quả.
- LoginPage: submit → gọi API, lưu token, redirect.
- Auth guard: chưa login → redirect `/login`.
- Mock API bằng MSW hoặc vi.mock axios. Không test styling thuần, không snapshot test.

## 9. Definition of Done

1. `uvicorn app.main:app` + `npm run dev` + gateway chạy đồng thời trên Windows.
2. CLI `create-admin` tạo được tài khoản, đăng nhập được trên Dashboard.
3. Import được danh sách proxy qua UI, hiện đúng bảng + stat cards.
4. `curl -x http://127.0.0.1:8899 http://target` đi ra internet qua proxy trong pool (verify với proxy thật hoặc mock target).
5. Request tự xoay IP giữa các proxy ở 2 request liên tiếp.
6. Internal API từ chối khi không có key.
7. Toàn bộ test backend + frontend pass (`pytest` + `npm test`).
8. README cập nhật: bỏ banner WIP cho phần đã xong, tick roadmap "MVP".

## 10. Rủi ro đã nhận diện

| Rủi ro | Xử lý |
|---|---|
| proxy.py không inject `Proxy-Authorization` cho upstream | Verify sớm bằng test tích hợp; fallback: plugin tự thêm header |
| `before_upstream_connection` không trả được 502 đẹp | Fallback: log + teardown; chấp nhận ở MVP, ghi chú |
| SQLite lock khi nhiều thread gateway gọi đồng thời | WAL + busy_timeout 5000ms đã thiết kế sẵn |

## 11. Ngoài phạm vi Phần 1

- Health check Celery (Phần 2), trang Settings.
- Multi-tenant, API key per user, proxy-auth gateway (Phần 3).
- Sticky session (Phần 4).
- WebSocket realtime logs, RequestLog (Phần 5).
- Docker Compose (Phần 6).
- Hỗ trợ socks5 qua gateway.
- Alembic migrations.
