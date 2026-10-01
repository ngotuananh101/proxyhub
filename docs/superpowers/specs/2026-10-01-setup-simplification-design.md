# Setup Simplification & Laravel-Style ENV — Design

**Date:** 2026-10-01
**Status:** Draft for review
**Scope:** Infrastructure/configuration only — no application behaviour change.

## 1. Problem

The run and setup steps feel heavy:

- **Docker Compose defines 7 services** (`postgres`, `redis`, `backend`, `celery_worker`,
  `celery_beat`, `gateway`, `frontend`). Four of them run the *same* Python image and the
  *same* codebase, differing only by command. Bringing the stack up means four near-identical
  build/run entries to read and manage.
- **The only one-command dev runner is `start-dev.bat`** — Windows-only, while the primary
  development machine is Linux. There is no equivalent for Linux/macOS, so local dev means
  five manual terminals (uvicorn, celery worker, celery beat, gateway, npm).
- **`.env` is a flat, ungrouped list.** Related keys (auth, database, queue, gateway) are not
  visually separated, there are no section banners, and one key (`REDIS_URL`) is dead.

## 2. Goals

1. Reformat `.env` in Laravel style — sectioned, commented, grouped — **and** rename keys to
   Laravel-style prefixes (`APP_*`, `DB_*`, `JWT_*`, `QUEUE_*`, `GATEWAY_*`).
2. Collapse Docker Compose from 7 services to **4** by running the Python processes under
   **supervisor** in one `app` container.
3. Replace `start-dev.bat` with a **cross-platform bootstrap script** that sets up and runs
   the whole local stack with one command.

## 3. Non-goals

- No change to application architecture, API surface, database schema, or auth semantics.
- No change to the frontend's `VITE_*` variables (Vite requires the `VITE_` prefix).
- No back-compat aliases for old env names — this is a **hard rename** (decided with the user).
- No unrelated refactoring.

## 4. Invariant: two different namespaces

There are two distinct sets of "setting" names, and only one may be renamed:

| Namespace | Example | Storage | Rename? |
|---|---|---|---|
| **Env vars** | `DATABASE_URL`, `SECRET_KEY` | `.env` / process env | ✅ Yes |
| **DB setting keys** | `HEALTH_CHECK_URL`, `TIMEZONE`, `REQUEST_LOG_RETENTION_DAYS` | `appsettings` table, seeded from env on first boot | ❌ **Never** |

The DB keys are returned verbatim by `GET /api/settings` and matched by name in the frontend
(`use-timezone.ts`, `SettingsPage.tsx`, `settings_registry.py`, `worker.py`). Renaming them
would silently break the Settings page and the worker. `settings_registry.py` seeds each DB
key's *default* from an env field (`default=settings.HEALTH_CHECK_URL`), so the **env field
may be renamed while the DB key stays the same** — the two are decoupled.

## 5. ENV rename map

### 5.1 Renamed

| Old | New | Notes |
|---|---|---|
| `SECRET_KEY` | `APP_KEY` | Laravel's `APP_KEY`. Used by `core/security.py`, `config.validate_secrets`. |
| `ALGORITHM` | `JWT_ALGORITHM` | Too generic a name. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `JWT_ACCESS_TOKEN_TTL` | Value stays in minutes. |
| `DATABASE_URL` | `DB_URL` | Kept as a full DSN (not split into `DB_HOST`/`DB_PORT`/…). |
| `POSTGRES_USER` | `DB_USERNAME` | Consumed by Compose (postgres service + healthcheck). |
| `POSTGRES_PASSWORD` | `DB_PASSWORD` | Consumed by Compose. |
| `POSTGRES_DB` | `DB_DATABASE` | Consumed by Compose. |
| `CELERY_BROKER_URL` | `QUEUE_BROKER_URL` | Laravel's `QUEUE_*` prefix. |
| `CELERY_RESULT_BACKEND` | `QUEUE_RESULT_BACKEND` | |
| `PORT` | `FRONTEND_PORT` | Host port for the dashboard. Name now says what it is. |

### 5.2 Added

| New | Default | Notes |
|---|---|---|
| `APP_NAME` | `ProxyHub` | Informational; documents the service. Not read by code. |
| `APP_ENV` | `local` | Informational; documents the environment (`local`/`production`). Not read by code. |
| `APP_PORT` | `8000` | Host port for the API. Previously hardcoded in Compose. |
| `VITE_API_URL` | *(empty)* | Moved into the root `.env` so the same file drives both dev and the Docker frontend build. Empty = same-origin (Nginx proxies `/api`). |
| `VITE_WS_URL` | *(empty)* | Same as above. |

### 5.3 Removed

| Old | Reason |
|---|---|
| `REDIS_URL` | Dead — no code reads it. Celery uses `QUEUE_BROKER_URL`/`QUEUE_RESULT_BACKEND`. |

### 5.4 Unchanged (kept for a reason)

| Key | Reason |
|---|---|
| `HEALTH_CHECK_URL/TIMEOUT/INTERVAL/CONCURRENCY`, `REQUEST_LOG_RETENTION_DAYS` | Env fields feed DB-key defaults; renaming the field is possible but adds churn with no readability gain. Grouped under a "Runtime settings" section instead. |
| `INTERNAL_API_KEY` | Cross-cutting shared secret between backend and gateway; no clean Laravel analogue. |
| `GATEWAY_API_URL`, `GATEWAY_SESSION_URL`, `GATEWAY_LOG_URL`, `GATEWAY_AUTH_CACHE_TTL` | Already prefixed. |
| `CORS_ORIGINS` | No Laravel analogue. |
| `GATEWAY_PORT` | Already correctly named. |
| `VITE_API_URL`, `VITE_WS_URL` | Vite requires the `VITE_` prefix. |

### 5.5 Resulting `.env.example` shape

```dotenv
############################################
# ProxyHub
############################################

APP_NAME=ProxyHub
APP_ENV=local
APP_KEY=change_me_to_a_random_secure_secret_key
APP_PORT=8000

#--------------------------------------------------
# Database
#--------------------------------------------------
DB_CONNECTION=postgresql
DB_URL=postgresql+psycopg://proxyhub:proxyhub@127.0.0.1:5432/proxyhub
DB_USERNAME=proxyhub
DB_PASSWORD=change_me_to_a_strong_password
DB_DATABASE=proxyhub

#--------------------------------------------------
# Queue (Celery / Redis)
#--------------------------------------------------
QUEUE_BROKER_URL=redis://127.0.0.1:6379/1
QUEUE_RESULT_BACKEND=redis://127.0.0.1:6379/2

#--------------------------------------------------
# Auth (JWT)
#--------------------------------------------------
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_TTL=1440
INTERNAL_API_KEY=change_me_to_a_random_internal_api_key

#--------------------------------------------------
# Gateway
#--------------------------------------------------
GATEWAY_API_URL=http://localhost:8000/internal/proxies
GATEWAY_SESSION_URL=http://localhost:8000/internal/gateway/session
GATEWAY_LOG_URL=http://localhost:8000/internal/logs
GATEWAY_AUTH_CACHE_TTL=60.0
GATEWAY_PORT=8899

#--------------------------------------------------
# Runtime settings (seeded to DB on first boot)
#--------------------------------------------------
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=6
HEALTH_CHECK_INTERVAL=300
HEALTH_CHECK_CONCURRENCY=50
REQUEST_LOG_RETENTION_DAYS=30

#--------------------------------------------------
# CORS
#--------------------------------------------------
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost

#--------------------------------------------------
# Frontend (Vite — dev server + Docker build args)
#--------------------------------------------------
# Leave empty in Docker to use same-origin (Nginx proxies /api and /ws).
VITE_API_URL=
VITE_WS_URL=
# Host port for the dashboard container.
FRONTEND_PORT=3000
```

> `DB_CONNECTION` is informational only (documents the driver); `DB_URL` remains the single
> source of truth. No `DB_HOST`/`DB_PORT`/`DB_NAME` split.

## 6. Docker Compose: 7 → 4 services

### 6.1 Before / after

| Before | After |
|---|---|
| `postgres` | `postgres` |
| `redis` | `redis` |
| `backend` (uvicorn) | `app` (supervisor → uvicorn + worker + beat + gateway) |
| `celery_worker` | ↑ |
| `celery_beat` | ↑ |
| `gateway` | ↑ |
| `frontend` | `frontend` |

### 6.2 The `app` container

- Same `Dockerfile` (Python image), now also installing `supervisor`.
- Supervisor runs four programs from one config (`deploy/supervisor.conf`):
  1. `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  2. `celery -A app.worker.celery_app worker --loglevel=info`
  3. `celery -A app.worker.celery_app beat --loglevel=info`
  4. `python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 0.0.0.0 --port 8899`
- Supervisor runs in the foreground (`nodaemon=true`) so it is PID 1; `autorestart=true` per
  program restarts a crashed process; logs go to stdout/stderr (`stdout_logfile=/dev/stdout`,
  `maxbytes=0`, `redirect_stderr=true`) so `docker compose logs -f app` shows everything.
- `app` exposes `127.0.0.1:${APP_PORT:-8000}:8000` and `127.0.0.1:${GATEWAY_PORT:-8899}:8899`.
- Because the gateway now shares the container, it talks to the API over the loopback:
  `GATEWAY_API_URL=http://127.0.0.1:8000/internal/proxies` (and session/log URLs likewise).
- Healthcheck: `curl -fsS http://127.0.0.1:8000/healthz` (`curl` is already in the image).

### 6.3 Postgres healthcheck

Uses `$${DB_USERNAME}` / `$${DB_DATABASE}`.

### 6.4 Frontend build args

`frontend/Dockerfile` gains `ARG VITE_API_URL` / `ARG VITE_WS_URL` (default empty) before
`npm run build`. Compose passes `build.args` from `VITE_*` so one `.env` configures both dev
and Docker. Empty values keep the same-origin default the SPA already uses.

## 7. Cross-platform dev bootstrap: `dev.py`

A stdlib-only Python script (no new dependencies) replacing `start-dev.bat`.

```
python dev.py setup     # venv + pip install + .env from .env.example + npm install + create-admin prompt
python dev.py run       # launch all 5 dev processes in one terminal, Ctrl+C stops all
python dev.py admin ... # passthrough to `python -m app.cli create-admin`
```

- Works on Linux, macOS, and Windows (uses `sys.executable`, `venv` paths per-OS).
- `setup` is idempotent: skips venv/npm if present, never overwrites an existing `.env`.
- `run` supervises the child processes itself: it starts each with `subprocess.Popen`, prefixes
  output by service name, and on `KeyboardInterrupt`/`SIGTERM` terminates the whole group.
- Processes match today's dev commands (uvicorn --reload, `npm run dev`, celery worker/beat,
  `python -m proxy`), with `--pool=threads` on Windows only.
- `start-dev.bat` is deleted.

## 8. New endpoint: `GET /healthz`

A tiny unauthenticated liveness route returning `{"status": "ok"}`, used by the `app`
container healthcheck. It must be exempt from any auth dependency (the app currently has no
global auth middleware, so a plain route suffices).

## 9. File-by-file change list

| File | Change |
|---|---|
| `.env.example` | Rewritten: sectioned Laravel style + new names + `APP_PORT` + `DB_CONNECTION`; drop `REDIS_URL`. |
| `app/core/config.py` | Field renames (`APP_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_TTL`, `DB_URL`, `QUEUE_*`); `validate_secrets` message/keys; remove unused `GATEWAY_API_URL`-style leftovers if any. |
| `app/core/security.py` | `settings.SECRET_KEY`→`APP_KEY`, `ALGORITHM`→`JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`→`JWT_ACCESS_TOKEN_TTL`. |
| `app/core/database.py` | `settings.DATABASE_URL`→`DB_URL`. |
| `app/core/settings_registry.py` | Defaults reference renamed env fields (DB keys unchanged). |
| `app/services/events.py` | `settings.CELERY_BROKER_URL`→`QUEUE_BROKER_URL`. |
| `app/worker.py` | `settings.CELERY_BROKER_URL`→`QUEUE_BROKER_URL`, `CELERY_RESULT_BACKEND`→`QUEUE_RESULT_BACKEND`. |
| `alembic/env.py` | `settings.DATABASE_URL`→`DB_URL`. |
| `scripts/migrate_sqlite_to_postgres.py` | `settings.DATABASE_URL`→`DB_URL` + messages. |
| `app/api/health.py` (new) + `app/main.py` | `GET /healthz` route + include router. |
| `docker-compose.yml` | Rewritten to 4 services; `app` runs supervisor; env overrides use new names. |
| `Dockerfile` | Install `supervisor`; copy `deploy/supervisor.conf`; CMD → `supervisord`. |
| `deploy/supervisor.conf` (new) | Four programs + `[supervisord]`. |
| `frontend/Dockerfile` | `ARG`/`ENV VITE_API_URL`, `VITE_WS_URL` before build. |
| `dev.py` (new), `start-dev.bat` (deleted) | Cross-platform bootstrap. |
| `tests/conftest.py`, `tests/test_config.py` | New env names; drop the stale `CELERY_*`/`REDIS_URL` lines. |
| `frontend/.env.example` | Kept as the **dev** template (absolute `http://localhost:8000`), copied by `dev.py setup`. Root `.env`'s `VITE_*` are the **Docker build** values (empty = same-origin). |
| `README.md` | Rewrite Quick Start / Manual Dev / Configuration sections; 7→4 services; `dev.py`; new env table. |

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| One crashed process in `app` is less visible | Supervisor `autorestart=true`; per-process stdout prefixes; healthcheck on `/healthz`. |
| Gateway and API share a container lifecycle | Accepted trade-off chosen by the user; they already share an image and the gateway depends on the API. |
| DB keys accidentally renamed | Explicit invariant (§4) + a test asserting DB keys are unchanged. |
| Existing deployments' `.env` breaks | Documented as a breaking change; README gives the old→new table; `validate_secrets` still fails fast with a clear message. |
| Supervisor restart loops hide config errors | `docker compose logs -f app` shows the failing program's traceback. |

## 11. Verification plan

- `ruff check app/ tests/ scripts/` → clean.
- `pytest --cov=app` → all tests pass; add a config test for the new field names and a test
  that DB setting keys are unchanged.
- `docker compose config` → valid; exactly 4 services.
- `docker compose up -d --build` → `app` healthy; `curl localhost:8000/healthz` OK;
  `curl -x http://localhost:8899 http://httpbin.org/ip` returns a proxy IP;
  `docker compose logs -f app` shows uvicorn + worker + beat + gateway.
- `python dev.py setup && python dev.py run` on Linux → all five processes start; Ctrl+C stops all.
- Frontend: `npm run build` with `VITE_API_URL` unset (same-origin) and with it set (absolute).
- CI unchanged in behaviour (still green).

## 12. Out of scope

- Compose profiles for infra-only dev.
- Splitting `DB_URL` into `DB_HOST`/`DB_PORT`/… parts.
- Renaming the DB setting keys (`HEALTH_CHECK_*`, `TIMEZONE`, …).
- Production hardening (TLS, non-root images, secrets manager).
