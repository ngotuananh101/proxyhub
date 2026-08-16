# ProxyHub — Part 1: MVP End-to-End (Design Spec)

- **Date:** 2026-08-15
- **Status:** Approved
- **Scope:** Part 1 of 6 in the roadmap (MVP, Health Check, Multi-tenant, Sticky Session, WebSocket Logs, Docker Compose)

## 1. Objectives

Run an end-to-end flow on native Windows:

```
curl -x http://127.0.0.1:8899 http://target
```

→ request goes out to the internet through a proxy in the pool, automatically rotates IP between requests, pool managed via a React Dashboard with JWT login.

### Foundational Decisions (applicable across the entire project)

| Decision | Choice |
|---|---|
| MVP Scope | Full-stack end-to-end (Backend + Gateway + Dashboard) |
| Auth | JWT from the MVP stage, user creation via CLI (no public registration) |
| Testing | pytest (backend) + Vitest/Testing Library (frontend) |
| Dev Environment | Native Windows: Redis via Memurai/Redis-Windows, Celery `--pool=solo` |
| Gateway proxy retrieval | Call internal API on every request (no caching in the plugin) |

## 2. Backend Architecture

```
app/
├── main.py              # FastAPI app, mount routers, create tables on startup
├── cli.py               # CLI: create-admin (argparse, no additional dependencies)
├── core/
│   ├── config.py        # pydantic-settings reads .env
│   ├── database.py      # SQLModel engine, SQLite WAL + busy_timeout=5000ms
│   └── security.py      # JWT encode/decode, password hashing (direct bcrypt)
├── models/              # SQLModel tables: User, Proxy
├── schemas/             # Pydantic request/response
├── api/
│   ├── deps.py          # get_current_user (JWT), verify_internal_key
│   ├── auth.py          # /api/auth/*
│   ├── proxies.py       # /api/proxies/*
│   ├── stats.py         # /api/stats/summary
│   └── internal.py      # /internal/proxies (X-Internal-Key)
├── services/
│   ├── proxy_service.py # parse/validate/import text, dedupe, proxy selection
│   └── auth_service.py  # login, user creation
└── gateway/
    └── plugin.py        # RotateProxyPlugin (runs as a separate process)
```

- Do not use Alembic in MVP: SQLModel `create_all()` on startup. Migrations will be added when the schema becomes more complex (Part 3).
- Ruff as the single linter/formatter for Python.
- Hash passwords using `bcrypt` directly (do not use `passlib` — passlib has a known bug with bcrypt ≥ 4.1).

## 3. Data Model

### User

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| username | str unique | |
| email | str unique, nullable | |
| hashed_password | str | bcrypt |
| is_admin | bool | default `false` |
| created_at | datetime | |

### Proxy

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| scheme | str | `http` / `https` (MVP — socks5 can be stored but gateway does not use it) |
| host | str | |
| port | int | |
| username / password | str nullable | upstream credentials |
| status | enum | `unknown` / `alive` / `dead`, default `unknown` |
| latency_ms | float nullable | left blank for Part 2 |
| last_checked_at | datetime nullable | left blank for Part 2 |
| created_at / updated_at | datetime | |

- Unique constraint: `(scheme, host, port)` for deduplication during import.
- `status` defaults to `unknown` because the MVP does not have health checks yet. The gateway selects proxies with `status != 'dead'` (accepting both `unknown` and `alive`). In Part 2, the gateway will only select `alive`.

## 4. API Design

### Auth — `/api/auth`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Body `{username, password}` → `{access_token, token_type: "bearer"}` |
| GET | `/api/auth/me` | Current user info (requires JWT) |

- JWT payload: `sub` (user id), `exp`. Expiration according to `ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440).
- No public registration endpoint — users are only created via the `create-admin` CLI. Registration is deferred to Part 3.

### Proxies — `/api/proxies` (requires JWT)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/proxies` | List + pagination (`?page=1&size=20`), filter `?status=&scheme=&q=` |
| POST | `/api/proxies` | Add 1 proxy (JSON body) |
| POST | `/api/proxies/import` | Body `{text}` — parse multiple lines → `{imported, duplicates, invalid: [{line, reason}]}` |
| GET | `/api/proxies/{id}` | Details of 1 proxy |
| PUT | `/api/proxies/{id}` | Edit host, port, credentials |
| DELETE | `/api/proxies/{id}` | Delete 1 proxy |
| DELETE | `/api/proxies` | Bulk delete: body `{ids: [...]}` |

### Stats — `/api/stats` (requires JWT)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/stats/summary` | `{total, alive, dead, unknown}` |

### Internal — `/internal` (requires header `X-Internal-Key`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/internal/proxies?strategy=random` | Returns 1 usable proxy: `{id, scheme, host, port, username, password}` |

Details:

- Proxy selection: query `status != 'dead'`, select randomly using Python `random.choice` (MVP pool is small, no SQL random needed).
- `strategy`: defaults to `random`; MVP only supports `random`, other values → `400`. Keeping the param so Part 4 can add `sticky` without breaking the API.
- No usable proxy → `404 {detail: "No available proxy"}`.
- Authentication: compare `X-Internal-Key` with `INTERNAL_API_KEY` in env (constant-time comparison). Invalid/missing → `401`.
- Only return fields needed by the gateway to connect upstream, without exposing other internal information.

### General Conventions

- Standard FastAPI errors: `400` validation error, `401` unauthorized, `404` not found, `409` duplicate proxy on single creation.
- Response schemas are separated from DB models (no exposure of `hashed_password`).
- CORS: allow `http://localhost:5173`, configured via env `CORS_ORIGINS`.

## 5. Gateway Plugin (`RotateProxyPlugin`)

### How to Run

```bash
proxy --plugin-name app.gateway.plugin.RotateProxyPlugin \
      --hostname 127.0.0.1 --port 8899 --threaded
```

- Threaded mode so the plugin's synchronous HTTP calls to the Backend do not block the event loop. Acceptable trade-off at MVP scale.
- Plugin reads config from env on startup: `GATEWAY_API_URL`, `INTERNAL_API_KEY`.

### Request Processing Flow

```
Client request → before_upstream_connection()
  ├─ GET {GATEWAY_API_URL}?strategy=random (timeout 2s, header X-Internal-Key)
  ├─ 200 → set request.upstream = http://[user:pass@]host:port → continue
  ├─ 404 (no available proxy) → log + teardown, return 502 "No available proxy"
  └─ Error/timeout (Backend down) → log + teardown, return 502 "Proxy service unavailable"
```

- Hook `before_upstream_connection`: call API and assign upstream; return `None` to reject the request. If the proxy.py mechanism does not allow returning a clean 502, the fallback is log + teardown (client receives connection reset) — acceptable in MVP, noted accordingly.
- Upstream proxy auth: plugin sets upstream URL with credentials. If proxy.py base plugin does not automatically inject `Proxy-Authorization`, the plugin manually adds the header (for both regular HTTP and CONNECT). Verify with integration tests during implementation.

### Design Principles

1. Plugin holds no state — each request is an independent API call. No caching, no automatic retry (if a request fails, the client retries and gets a different IP — which is "proxy rotation").
2. No client authentication in MVP — gateway binds to `127.0.0.1`. Per-user proxy-auth is deferred to Part 3.
3. Minimal logging: 1 line per request (selected proxy, target host, result) to stdout using Python logging. Logging to DB is deferred to Part 5.
4. No loop-prevention in MVP (blocking requests directed at the Backend itself) — handled in Part 5/6.

## 6. Frontend (React Dashboard)

### Stack & Structure

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts        # Axios: baseURL from VITE_API_URL, attaches Authorization, 401 → redirect login
│   │   ├── auth.ts          # login(), me()
│   │   └── proxies.ts       # list/create/import/update/delete, stats
│   ├── components/
│   │   ├── ui/              # shadcn/ui
│   │   ├── ProxyTable.tsx   # Proxy table + filter + pagination
│   │   ├── ImportDialog.tsx # Paste text to import multiple proxies
│   │   ├── ProxyForm.tsx    # Form to add/edit 1 proxy
│   │   └── StatCards.tsx    # Total/Alive/Dead/Unknown
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   └── ProxiesPage.tsx  # Only main page for MVP
│   ├── lib/auth.ts          # Token in localStorage, useAuth hook
│   ├── App.tsx              # Router: /login, / (protected)
│   └── main.tsx
├── .env.example             # VITE_API_URL, VITE_WS_URL (ready for Part 5)
└── package.json
```

### Screens

**Login (`/login`):** username/password form → `/api/auth/login` → save token to localStorage → navigate to `/`. If a valid token already exists, redirect directly to `/`.

**Proxies (`/`):**

- Top row of StatCards (calls `/api/stats/summary`).
- Toolbar: host search input, status filter (All/Alive/Dead/Unknown), Add Proxy / Import / Delete selected buttons.
- ProxyTable: checkbox, scheme (badge), host:port, credentials (masked, revealed by clicking 👁), status (colored badge), latency (— in MVP), created_at, edit/delete actions. Pagination at 20 rows/page.
- ImportDialog: multi-line paste textarea → `/api/proxies/import` → display `imported / duplicates / invalid` (with reasons for each invalid line) → reload table.
- ProxyForm (dialog): scheme (http/https only — socks5 disabled with tooltip "not supported via gateway yet"), host, port, username, password.

### Conventions

- React Query (TanStack Query) for data fetching — cache, loading/error, invalidate after mutation.
- React Router v6, route `/` wrapped in a token verification guard.
- Tailwind + shadcn/ui, dark mode by default.
- Out of scope for MVP: Settings page (Part 2), realtime logs (Part 5), user/pool management (Part 3).

## 7. Scaffold & Dependencies

```
proxyhub/
├── app/                    # Backend
├── frontend/               # React
├── tests/                  # pytest: unit + integration backend
├── requirements.txt        # fastapi, uvicorn, sqlmodel, pydantic-settings,
│                           #   celery (pre-installed for Part 2), proxy.py, bcrypt,
│                           #   PyJWT, httpx, python-multipart
├── requirements-dev.txt    # pytest, pytest-asyncio, ruff
├── .env.example            # Like README + INTERNAL_API_KEY + CORS_ORIGINS
├── .gitignore              # venv, .env, *.db, node_modules, dist
├── pyproject.toml          # ruff + pytest config
└── README.md, LICENSE      # Already present
```

## 8. Testing Strategy

### Backend (pytest)

| Group | What to Test |
|---|---|
| `proxy_service` | Text import parsing: valid lines, invalid lines (wrong scheme, missing port, malformed URL), deduplication, socks5 excluded from gateway selection |
| Auth | Login with correct/wrong password, expired JWT, endpoint without token → 401 |
| Proxies API | Full CRUD, filter/pagination, import returns correct counts, bulk delete |
| Internal API | No key → 401, invalid key → 401, with key → returns `unknown`/`alive` proxy, does not return `dead`, no proxy available → 404 |
| Gateway plugin | Mock Backend: 200/404/timeout |
| Integration | Run real uvicorn + gateway with temp DB, `curl -x` via mock target server → assert IP matches proxy |

### Frontend (Vitest + Testing Library)

- ProxyTable: render mock list, filter by status.
- ImportDialog: submit text → call correct API, display results.
- LoginPage: submit → call API, save token, redirect.
- Auth guard: unauthenticated → redirect `/login`.
- Mock API using MSW or vi.mock axios. Do not test pure styling, no snapshot tests.

## 9. Definition of Done

1. `uvicorn app.main:app` + `npm run dev` + gateway running concurrently on Windows.
2. CLI `create-admin` can create an account, which can log into the Dashboard.
3. Successfully import proxy list via UI, correctly displaying the table + stat cards.
4. `curl -x http://127.0.0.1:8899 http://target` routes out to the internet through a proxy in the pool (verified with real proxy or mock target).
5. Requests automatically rotate IP across proxies on consecutive requests.
6. Internal API rejects requests without a key.
7. All backend + frontend tests pass (`pytest` + `npm test`).
8. README updated: remove WIP banner for completed sections, check off "MVP" on roadmap.

## 10. Identified Risks

| Risk | Mitigation |
|---|---|
| proxy.py does not inject `Proxy-Authorization` for upstream | Verify early via integration tests; fallback: plugin manually adds header |
| `before_upstream_connection` cannot return a clean 502 | Fallback: log + teardown; acceptable in MVP, noted accordingly |
| SQLite lock when multiple gateway threads call concurrently | WAL + busy_timeout 5000ms already designed in |

## 11. Out of Scope for Part 1

- Celery health check (Part 2), Settings page.
- Multi-tenant, per-user API keys, gateway proxy-auth (Part 3).
- Sticky session (Part 4).
- WebSocket realtime logs, RequestLog (Part 5).
- Docker Compose (Part 6).
- socks5 support via gateway.
- Alembic migrations.
