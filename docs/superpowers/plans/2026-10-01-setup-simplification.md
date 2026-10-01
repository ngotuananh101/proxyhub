# Setup Simplification & Laravel-Style ENV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every environment variable to a Laravel-style prefix, collapse Docker Compose from 7 services to 4 via supervisor, and replace the Windows-only `start-dev.bat` with a cross-platform `dev.py` bootstrap.

**Architecture:** Purely infrastructure/configuration. The Python app keeps its shape; only the names it reads from the environment change. Four Python processes (uvicorn, celery worker, celery beat, proxy gateway) move from four Compose services into one `app` container managed by supervisor. A new stdlib-only `dev.py` drives the manual (non-Docker) workflow.

**Tech Stack:** Python 3.10+ / pydantic-settings, FastAPI, Celery, supervisor, Docker Compose, Vite/React, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-setup-simplification-design.md`

## Global Constraints

- **Hard rename, no back-compat aliases.** Old names (`DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `POSTGRES_*`, `CELERY_*`, `PORT`) must not appear anywhere after the rename except in the README's old→new migration table.
- **Never rename DB setting keys.** `HEALTH_CHECK_URL`, `HEALTH_CHECK_TIMEOUT`, `HEALTH_CHECK_INTERVAL`, `HEALTH_CHECK_CONCURRENCY`, `REQUEST_LOG_RETENTION_DAYS`, `SOURCE_FETCH_TIMEOUT`, `DEAD_PROXY_RETENTION_DAYS`, `TIMEZONE` are keys in the `appsettings` table and are matched by name in `app/core/settings_registry.py`, `app/worker.py`, and the frontend (`use-timezone.ts`, `SettingsPage.tsx`). Their *env-field* sources may be renamed; their *key strings* may not.
- **`VITE_API_URL` / `VITE_WS_URL` keep the `VITE_` prefix** — Vite only exposes `VITE_`-prefixed vars.
- **`INTERNAL_API_KEY`, `CORS_ORIGINS`, `GATEWAY_*`, `HEALTH_CHECK_*`, `REQUEST_LOG_RETENTION_DAYS` keep their names.**
- **No new runtime dependency except `supervisor`** (Docker only). `dev.py` uses the standard library only.
- **Line length 100, ruff rules `E,F,I,W`** (from `pyproject.toml`).
- Compose must define **exactly 4 services**: `app`, `postgres`, `redis`, `frontend`.

## Review Focus

These are the input classes / failure modes the spec implies but no task's unit tests can reach. Each is pinned to a verification step in the task that owns the code.

1. **Unset `DB_PASSWORD` at `docker compose up`** — must fail fast with a message naming `DB_PASSWORD`, not start a broken stack. (Task 3, Step 7.)
2. **Stale `.env` from before the rename** — startup must fail with a message naming `APP_KEY`/`INTERNAL_API_KEY`, not silently run or crash with an obscure error. (Task 1, Step 5.)
3. **A supervised program crashing inside `app`** — must not take the container down; supervisor restarts it and the failure is visible in logs. (Task 3, Step 8.)
4. **Empty `VITE_API_URL` in the Docker frontend build** — must produce a same-origin build (Nginx proxies `/api`), not a build that points at nothing. (Task 3, Step 9.)
5. **`Ctrl+C` on `dev.py run`** — must stop every child process, leaving no orphaned uvicorn/celery/gateway/npm. (Task 4, Step 6.)

---

### Task 1: Rename environment variables in the backend

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/core/security.py:23,26,30`
- Modify: `app/core/database.py:10,21,26`
- Modify: `app/core/settings_registry.py:6-7` (docstring only)
- Modify: `app/services/events.py:56,82`
- Modify: `app/worker.py:29,30`
- Modify: `alembic/env.py:20,30`
- Modify: `scripts/migrate_sqlite_to_postgres.py:7,83,84,87,88`
- Modify: `tests/conftest.py:7,8`
- Modify: `tests/test_config.py`
- Rewrite: `.env.example`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the canonical `Settings` field names every later task depends on — `settings.DB_URL`, `settings.APP_KEY`, `settings.JWT_ALGORITHM`, `settings.JWT_ACCESS_TOKEN_TTL`, `settings.QUEUE_BROKER_URL`, `settings.QUEUE_RESULT_BACKEND`. Env var names in `.env`: `DB_URL`, `APP_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_TTL`, `QUEUE_BROKER_URL`, `QUEUE_RESULT_BACKEND`, `DB_USERNAME`, `DB_PASSWORD`, `DB_DATABASE`, `APP_PORT`, `FRONTEND_PORT`.

- [ ] **Step 1: Update the config tests to the new names (failing test first)**

Replace `tests/test_config.py` with:

```python
# tests/test_config.py
import pytest

from app.core.config import Settings, validate_secrets


def test_settings_defaults():
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_ACCESS_TOKEN_TTL == 1440
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_settings_cors_parsing():
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
        CORS_ORIGINS="http://a.com,http://b.com",
    )
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_settings_ignores_extra_env_vars(monkeypatch):
    # Values that live only in .env.example / docker-compose must not break
    # startup when Settings does not declare them.
    monkeypatch.setenv("QUEUE_BROKER_URL", "redis://127.0.0.1:6379/1")
    monkeypatch.setenv("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
    s = Settings(
        _env_file=None,
        DB_URL="sqlite:///./test.db",
        APP_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.DB_URL == "sqlite:///./test.db"


def test_queue_and_health_check_defaults(monkeypatch):
    for key in (
        "QUEUE_BROKER_URL",
        "QUEUE_RESULT_BACKEND",
        "HEALTH_CHECK_URL",
        "HEALTH_CHECK_TIMEOUT",
        "HEALTH_CHECK_INTERVAL",
        "HEALTH_CHECK_CONCURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.QUEUE_BROKER_URL == "redis://127.0.0.1:6379/1"
    assert s.QUEUE_RESULT_BACKEND == "redis://127.0.0.1:6379/2"
    assert s.HEALTH_CHECK_URL == "https://api.ipify.org"
    assert s.HEALTH_CHECK_TIMEOUT == 6.0
    assert s.HEALTH_CHECK_INTERVAL == 300.0
    assert s.HEALTH_CHECK_CONCURRENCY == 50


def test_validate_secrets_accepts_real_values():
    s = Settings(
        _env_file=None,
        APP_KEY="a-real-random-secret",
        INTERNAL_API_KEY="a-real-internal-key",
    )
    validate_secrets(s)  # must not raise


@pytest.mark.parametrize("bad", ["change_me", ""])
def test_validate_secrets_rejects_placeholders(bad):
    s = Settings(
        _env_file=None,
        APP_KEY=bad,
        INTERNAL_API_KEY=bad,
    )
    with pytest.raises(RuntimeError, match="APP_KEY, INTERNAL_API_KEY"):
        validate_secrets(s)


def test_validate_secrets_names_only_unset_keys():
    s = Settings(
        _env_file=None,
        APP_KEY="a-real-random-secret",
        INTERNAL_API_KEY="change_me",
    )
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY") as exc_info:
        validate_secrets(s)
    assert "APP_KEY" not in str(exc_info.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL — `TypeError`/validation errors because `Settings` still declares `DATABASE_URL`/`SECRET_KEY`, and `s.JWT_ALGORITHM` does not exist.

- [ ] **Step 3: Rename the fields in `app/core/config.py`**

Replace the whole file with:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_URL: str = "sqlite:///./proxyhub.db"
    APP_KEY: str = "change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_TTL: int = 1440
    INTERNAL_API_KEY: str = "change_me"
    CORS_ORIGINS: str = "http://localhost:5173"
    QUEUE_BROKER_URL: str = "redis://127.0.0.1:6379/1"
    QUEUE_RESULT_BACKEND: str = "redis://127.0.0.1:6379/2"
    HEALTH_CHECK_URL: str = "https://api.ipify.org"
    HEALTH_CHECK_TIMEOUT: float = 6.0
    HEALTH_CHECK_INTERVAL: float = 300.0
    HEALTH_CHECK_CONCURRENCY: int = 50
    REQUEST_LOG_RETENTION_DAYS: int = 30
    GATEWAY_AUTH_CACHE_TTL: float = 60.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# Placeholder values that must never reach a running deployment.
INSECURE_PLACEHOLDERS = {"", "change_me"}


def validate_secrets(s: Settings) -> None:
    """Fail fast if auth secrets are still placeholder values.

    Called at server/worker startup so a deployment that forgot to set
    APP_KEY or INTERNAL_API_KEY cannot silently run with values
    anyone can guess.
    """
    unset = [
        name
        for name in ("APP_KEY", "INTERNAL_API_KEY")
        if getattr(s, name) in INSECURE_PLACEHOLDERS
    ]
    if unset:
        raise RuntimeError(
            "Refusing to start with insecure default secrets: "
            + ", ".join(unset)
            + ". Set real values in .env (see .env.example)."
        )
```

- [ ] **Step 4: Update every reader of the renamed fields**

`app/core/security.py` — replace `settings.ACCESS_TOKEN_EXPIRE_MINUTES` with `settings.JWT_ACCESS_TOKEN_TTL` (line 23), `settings.SECRET_KEY` with `settings.APP_KEY` and `settings.ALGORITHM` with `settings.JWT_ALGORITHM` (lines 26 and 30):

```python
def create_access_token(data: dict, expires_delta: int | None = None) -> str:
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_TTL
        )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.APP_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.APP_KEY, algorithms=[settings.JWT_ALGORITHM])
```

`app/core/database.py` — replace all three `settings.DATABASE_URL` with `settings.DB_URL` (lines 10, 21, 26).

`app/services/events.py` — replace both `settings.CELERY_BROKER_URL` with `settings.QUEUE_BROKER_URL` (lines 56, 82).

`app/worker.py` — in the `Celery(...)` call:

```python
celery_app = Celery(
    "proxyhub",
    broker=settings.QUEUE_BROKER_URL,
    backend=settings.QUEUE_RESULT_BACKEND,
)
```

`alembic/env.py` — replace both `settings.DATABASE_URL` with `settings.DB_URL` (lines 20, 30).

`scripts/migrate_sqlite_to_postgres.py` — replace `settings.DATABASE_URL` with `settings.DB_URL` (lines 83, 87, 88) and update the two user-facing strings to say `DB_URL`:

```python
    if settings.DB_URL.startswith("sqlite"):
        sys.exit("DB_URL still points at SQLite; set it to a PostgreSQL URL first.")

    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else "./proxyhub.db"
    print(f"Migrating {sqlite_path} -> {settings.DB_URL.split('@')[-1]}")
    migrate(f"sqlite:///{sqlite_path}", settings.DB_URL)
```

Also update the module docstring line 7 `DATABASE_URL must point at PostgreSQL` → `DB_URL must point at PostgreSQL`.

`app/core/settings_registry.py` — docstring only (lines 6-7): change `(DATABASE_URL, SECRET_KEY, CELERY_*, INTERNAL_API_KEY, CORS_ORIGINS)` to `(DB_URL, APP_KEY, QUEUE_*, INTERNAL_API_KEY, CORS_ORIGINS)`. The `key=` strings and `default=settings.HEALTH_CHECK_*` references are unchanged.

`tests/conftest.py` — lines 7-8:

```python
os.environ.setdefault("DB_URL", "sqlite:///./test.db")
os.environ.setdefault("APP_KEY", "test-secret-key-for-proxyhub-0123456789")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
```

- [ ] **Step 5: Run the config tests and the full suite**

Run: `pytest tests/test_config.py -q`
Expected: PASS (7 passed).

Run: `pytest -q`
Expected: all tests pass, same count as before the change.

- [ ] **Step 6: Verify no old names remain in code or config**

Run:
```bash
grep -rn "DATABASE_URL\|SECRET_KEY\|ACCESS_TOKEN_EXPIRE_MINUTES\|CELERY_BROKER_URL\|CELERY_RESULT_BACKEND\|POSTGRES_USER\|POSTGRES_PASSWORD\|POSTGRES_DB" \
  app/ tests/ scripts/ alembic/ .env.example docker-compose.yml start-dev.bat
```
Expected: no output (docker-compose and start-dev are updated in Tasks 3–4; if you run this before them, only those two files may still match — that is acceptable mid-plan, but they MUST be clean by the end of Task 4).

- [ ] **Step 7: Rewrite `.env.example` in Laravel style**

```dotenv
############################################
# ProxyHub
############################################

APP_NAME=ProxyHub
APP_ENV=local
APP_KEY=change_me_to_a_random_secure_secret_key
APP_PORT=8000

#--------------------------------------------------
# Database (PostgreSQL)
#--------------------------------------------------
# Local:  postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/proxyhub
# Docker: auto-configured in docker-compose.yml from DB_USERNAME/DB_PASSWORD/DB_DATABASE
# SQLite still works for single-process setups: sqlite:///./proxyhub.db
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
# Runtime settings (seeded to the DB on first boot, editable in the dashboard)
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
# Frontend (Vite: dev server + Docker build args)
#--------------------------------------------------
# Leave empty in Docker to use same-origin (Nginx proxies /api and /ws).
VITE_API_URL=
VITE_WS_URL=
# Host port for the dashboard container.
FRONTEND_PORT=3000
```

- [ ] **Step 8: Lint and commit**

Run: `ruff check app/ tests/ scripts/`
Expected: `All checks passed!`

```bash
git add app/core/config.py app/core/security.py app/core/database.py \
  app/core/settings_registry.py app/services/events.py app/worker.py \
  alembic/env.py scripts/migrate_sqlite_to_postgres.py \
  tests/conftest.py tests/test_config.py .env.example
git commit -m "refactor: rename env vars to Laravel-style prefixes"
```

---

### Task 2: Add a liveness endpoint for the container healthcheck

**Files:**
- Create: `app/api/health.py`
- Modify: `app/main.py` (import + `include_router`)
- Test: `tests/test_health_api.py`

**Interfaces:**
- Consumes: `create_app(db_engine)` from `app.main` (existing).
- Produces: `GET /healthz` → `200 {"status": "ok"}`, unauthenticated. Task 3's Compose healthcheck depends on this exact path and body shape.

- [ ] **Step 1: Write the failing test**

Create `tests/test_health_api.py`:

```python
from fastapi.testclient import TestClient


def test_healthz_returns_ok_without_auth(engine):
    from app.main import create_app

    with TestClient(create_app(engine)) as client:
        resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_health_api.py -q`
Expected: FAIL — `404 Not Found`.

- [ ] **Step 3: Add the route**

Create `app/api/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe for the container healthcheck. No auth, no DB access."""
    return {"status": "ok"}
```

- [ ] **Step 4: Register the router**

In `app/main.py`, add the import next to the other router imports:

```python
from app.api.health import router as health_router
```

and add the include line with the others:

```python
    app.include_router(health_router)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_health_api.py -q`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

Run: `ruff check app/ tests/`
Expected: `All checks passed!`

```bash
git add app/api/health.py app/main.py tests/test_health_api.py
git commit -m "feat: add unauthenticated /healthz liveness endpoint"
```

---

### Task 3: Collapse Compose to 4 services with supervisor

**Files:**
- Create: `deploy/supervisor.conf`
- Modify: `Dockerfile`
- Modify: `requirements.txt` (add `supervisor`)
- Rewrite: `docker-compose.yml`
- Modify: `frontend/Dockerfile` (build args)
- Modify: `frontend/nginx.conf:19,29` (`backend:8000` → `app:8000`)
- Modify: `frontend/nginx-proxy.conf:16,28,54,66,73` (`backend:8000` → `app:8000`)

**Interfaces:**
- Consumes: `GET /healthz` (Task 2); env names `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `DB_DATABASE`, `QUEUE_BROKER_URL`, `QUEUE_RESULT_BACKEND`, `APP_PORT`, `GATEWAY_PORT`, `FRONTEND_PORT` (Task 1).
- Produces: Compose service `app` reachable on the Compose network as `app:8000` (used by `frontend/nginx.conf`); container ports `127.0.0.1:${APP_PORT:-8000}` and `127.0.0.1:${GATEWAY_PORT:-8899}`.

- [ ] **Step 1: Add supervisor to the Python requirements**

Append to `requirements.txt`:

```
supervisor>=4.2.5
```

- [ ] **Step 2: Write the supervisor config**

Create `deploy/supervisor.conf`:

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:api]
command=uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/app
autostart=true
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

[program:worker]
command=celery -A app.worker.celery_app worker --loglevel=info
directory=/app
autostart=true
autorestart=true
priority=20
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

[program:beat]
command=celery -A app.worker.celery_app beat --loglevel=info
directory=/app
autostart=true
autorestart=true
priority=20
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

[program:gateway]
command=python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 0.0.0.0 --port 8899
directory=/app
autostart=true
autorestart=true
priority=30
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
```

- [ ] **Step 3: Update the Dockerfile**

Replace `Dockerfile` with:

```dockerfile
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/
COPY scripts/ ./scripts/

# One container runs api + worker + beat + gateway under supervisor.
COPY deploy/supervisor.conf /etc/supervisor/conf.d/proxyhub.conf

EXPOSE 8000 8899

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/proxyhub.conf"]
```

- [ ] **Step 4: Add the Vite build args to the frontend Dockerfile**

In `frontend/Dockerfile`, replace the build stage's `COPY . .` / `RUN npm run build` block with:

```dockerfile
COPY . .

# Vite reads these at build time. Empty means same-origin (Nginx proxies /api).
ARG VITE_API_URL=""
ARG VITE_WS_URL=""
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build
```

- [ ] **Step 5: Point the frontend nginx at the `app` service**

In `frontend/nginx.conf` replace both `proxy_pass http://backend:8000;` with `proxy_pass http://app:8000;` (lines 19, 29).

In `frontend/nginx-proxy.conf` replace every `backend:8000` with `app:8000` (lines 16, 28, 54, 66, 73) and update the two comments that say `backend:8000` (lines 14, and any other occurrence) to say `app:8000`.

- [ ] **Step 6: Rewrite `docker-compose.yml` with 4 services**

```yaml
services:
  redis:
    image: redis:8-alpine
    container_name: proxyhub-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - proxyhub-network

  postgres:
    image: postgres:18-alpine
    container_name: proxyhub-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${DB_USERNAME:-proxyhub}
      - "POSTGRES_PASSWORD=${DB_PASSWORD:?set DB_PASSWORD in .env}"
      - POSTGRES_DB=${DB_DATABASE:-proxyhub}
    volumes:
      # postgres:18+ expects the mount at /var/lib/postgresql and stores
      # data in a version-specific subdirectory (enables pg_upgrade).
      - postgres_data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${DB_USERNAME:-proxyhub} -d $${DB_DATABASE:-proxyhub}"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 15s
    networks:
      - proxyhub-network

  # One container runs the API, Celery worker, Celery beat, and the proxy
  # gateway under supervisor (see deploy/supervisor.conf).
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proxyhub-app
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - DB_URL=postgresql+psycopg://${DB_USERNAME:-proxyhub}:${DB_PASSWORD}@postgres:5432/${DB_DATABASE:-proxyhub}
      - QUEUE_BROKER_URL=redis://redis:6379/1
      - QUEUE_RESULT_BACKEND=redis://redis:6379/2
      # Gateway shares this container, so it reaches the API over loopback.
      - GATEWAY_API_URL=http://127.0.0.1:8000/internal/proxies
      - GATEWAY_SESSION_URL=http://127.0.0.1:8000/internal/gateway/session
      - GATEWAY_LOG_URL=http://127.0.0.1:8000/internal/logs
    ports:
      - "127.0.0.1:${APP_PORT:-8000}:8000"
      - "127.0.0.1:${GATEWAY_PORT:-8899}:8899"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - proxyhub-network

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_URL: ${VITE_API_URL:-}
        VITE_WS_URL: ${VITE_WS_URL:-}
    container_name: proxyhub-frontend
    restart: unless-stopped
    ports:
      - "127.0.0.1:${FRONTEND_PORT:-3000}:80"
    depends_on:
      app:
        condition: service_started
    networks:
      - proxyhub-network

volumes:
  postgres_data:
  redis_data:

networks:
  proxyhub-network:
    driver: bridge
```

- [ ] **Step 7: Verify the Compose file resolves to 4 services**

Run: `docker compose config --services`
Expected: exactly four lines — `redis`, `postgres`, `app`, `frontend`.

Run: `DB_PASSWORD= docker compose config -q` with a `.env` that has no `DB_PASSWORD`
Expected: non-zero exit with a message containing `set DB_PASSWORD in .env`.

- [ ] **Step 8: Build and bring the stack up**

Run: `docker compose up -d --build`
Expected: all four services start; `docker compose ps` shows `app` as `healthy`.

Run: `curl -fsS http://localhost:8000/healthz`
Expected: `{"status":"ok"}`.

Run: `docker compose logs app | grep -E "Booting worker|beat|RotateProxyPlugin|Uvicorn running"`
Expected: lines from the worker, beat, gateway, and API — proving supervisor started all four.

- [ ] **Step 9: Verify the gateway path and the empty-Vite build**

Run: `curl -x http://127.0.0.1:8899 http://httpbin.org/ip`
Expected: a JSON body with an `origin` IP (a pooled proxy).

Run: `docker compose exec frontend grep -ro "VITE_API_URL" /usr/share/nginx/html/assets | head -1`
Expected: no output — with empty `VITE_API_URL` the built bundle uses same-origin paths, so the literal is not present.

Run: `curl -fsS http://localhost:3000/api/settings -o /dev/null -w "%{http_code}\n"`
Expected: `401` (reachable through Nginx; auth required) — proving the frontend proxies `/api` to `app:8000`.

- [ ] **Step 10: Tear down and commit**

Run: `docker compose down`

```bash
git add deploy/supervisor.conf Dockerfile requirements.txt docker-compose.yml \
  frontend/Dockerfile frontend/nginx.conf frontend/nginx-proxy.conf
git commit -m "build: run api/worker/beat/gateway in one supervisor container"
```

---

### Task 4: Replace `start-dev.bat` with a cross-platform `dev.py`

**Files:**
- Create: `dev.py`
- Delete: `start-dev.bat`

**Interfaces:**
- Consumes: env names from Task 1 (`.env` / `frontend/.env` templates), `app.cli` (existing `create-admin`).
- Produces: `python dev.py setup`, `python dev.py run`, `python dev.py admin <args>`.

- [ ] **Step 1: Write `dev.py`**

```python
#!/usr/bin/env python3
"""Cross-platform dev bootstrap for ProxyHub.

Commands:
    python dev.py setup    # create venv, install deps, create .env files, npm install
    python dev.py run      # run api + frontend + gateway + celery worker + beat
    python dev.py admin    # passthrough to `python -m app.cli create-admin`
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WINDOWS = os.name == "nt"
VENV_DIR = ROOT / "venv"
VENV_BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
PY = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")
FRONTEND = ROOT / "frontend"


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd, shell=IS_WINDOWS)


def ensure_env_file(src: Path, dst: Path) -> None:
    if dst.exists():
        print(f"= {dst.relative_to(ROOT)} already exists, leaving it untouched")
        return
    if not src.exists():
        print(f"! {src.relative_to(ROOT)} not found; skipping")
        return
    shutil.copyfile(src, dst)
    print(f"+ created {dst.relative_to(ROOT)} from {src.name}")


def setup(_args: argparse.Namespace) -> None:
    if not PY.exists():
        print("+ creating virtualenv in ./venv")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    run([str(PY), "-m", "pip", "install", "-r", "requirements-dev.txt"])
    ensure_env_file(ROOT / ".env.example", ROOT / ".env")
    ensure_env_file(FRONTEND / ".env.example", FRONTEND / ".env")
    if (FRONTEND / "node_modules").exists():
        print("= frontend/node_modules already present")
    else:
        run(["npm", "install"], cwd=FRONTEND)
    print(
        "\nSetup done. Before production use, edit .env "
        "(APP_KEY, INTERNAL_API_KEY, DB_PASSWORD)."
    )


def _dev_commands() -> list[tuple[str, list[str]]]:
    # Celery needs the threads pool on Windows; the default prefork pool is
    # unsupported there.
    worker_pool = ["--pool=threads", "--concurrency=8"] if IS_WINDOWS else []
    return [
        (
            "api",
            [
                str(VENV_BIN / "uvicorn"),
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
        ),
        ("frontend", ["npm", "run", "dev"]),
        (
            "gateway",
            [
                str(PY),
                "-m",
                "proxy",
                "--plugins",
                "app.gateway.plugin.RotateProxyPlugin",
                "--hostname",
                "127.0.0.1",
                "--port",
                "8899",
            ],
        ),
        (
            "worker",
            [
                str(VENV_BIN / "celery"),
                "-A",
                "app.worker.celery_app",
                "worker",
                "--loglevel=info",
                *worker_pool,
            ],
        ),
        (
            "beat",
            [
                str(VENV_BIN / "celery"),
                "-A",
                "app.worker.celery_app",
                "beat",
                "--loglevel=info",
            ],
        ),
    ]


def run_services(_args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")

    procs: list[tuple[str, subprocess.Popen]] = []
    for name, cmd in _dev_commands():
        cwd = FRONTEND if name == "frontend" else ROOT
        print(f"+ starting {name}: {' '.join(cmd)}", flush=True)
        procs.append((name, subprocess.Popen(cmd, cwd=cwd, shell=IS_WINDOWS)))

    stopping = False

    def shutdown(*_args: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\n+ stopping services...", flush=True)
        for _name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for _name, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"! {name} exited with code {code}; stopping the rest")
                    shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


def admin(args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")
    run([str(PY), "-m", "app.cli", "create-admin", *args.rest])


def main() -> None:
    parser = argparse.ArgumentParser(prog="dev.py", description="ProxyHub dev bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="create venv, install deps, create .env files")
    sub.add_parser("run", help="run all dev services in one terminal")
    admin_parser = sub.add_parser("admin", help="create an admin user")
    admin_parser.add_argument("rest", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    {"setup": setup, "run": run_services, "admin": admin}[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete the Windows-only script**

```bash
git rm start-dev.bat
```

- [ ] **Step 3: Verify the CLI surface**

Run: `python dev.py --help`
Expected: shows the three subcommands `setup`, `run`, `admin`.

Run: `python dev.py run` (with no venv present)
Expected: exits with `No venv found. Run \`python dev.py setup\` first.`

- [ ] **Step 4: Run setup end to end**

Run: `python dev.py setup`
Expected: creates `venv/` if missing, installs `requirements-dev.txt`, creates `.env` and `frontend/.env` from their examples (or reports they already exist), installs `frontend/node_modules` if missing. Re-running it is a no-op for existing files.

- [ ] **Step 5: Start the stack**

Run: `python dev.py run`
Expected: five `+ starting ...` lines, then interleaved output from `api`, `frontend`, `gateway`, `worker`, `beat`. In another terminal, `curl -fsS http://127.0.0.1:8000/healthz` returns `{"status":"ok"}`.

- [ ] **Step 6: Verify Ctrl+C leaves no orphans**

Press `Ctrl+C` in the `dev.py run` terminal.
Expected: `+ stopping services...` prints and the command returns.

Then run: `pgrep -af "uvicorn|celery|proxy.py|vite" || echo "no orphans"`
Expected: `no orphans`.

- [ ] **Step 7: Commit**

```bash
git add dev.py
git commit -m "feat: add cross-platform dev.py bootstrap, drop start-dev.bat"
```

---

### Task 5: Update the README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above — 4 services, `dev.py`, `/healthz`, the new env names.
- Produces: nothing code-facing (docs only).

- [ ] **Step 1: Update the service count and names in Quick Start**

Replace the line `Docker Compose runs all 7 services (\`frontend\`, \`backend\`, \`celery_worker\`, \`celery_beat\`, \`gateway\`, \`postgres\`, \`redis\`) with persistent volumes in a single command.` with:

```markdown
Docker Compose runs all 4 services (`app`, `frontend`, `postgres`, `redis`) with persistent volumes in a single command. The `app` container runs the API, the Celery worker and beat, and the proxy gateway together under supervisor.
```

- [ ] **Step 2: Update the service-logs examples**

Replace `docker compose logs -f gateway` / `docker compose logs -f celery_worker` with:

```markdown
- **View specific service logs:** `docker compose logs -f app` (API + worker + beat + gateway) or `docker compose logs -f frontend`
```

Replace the Troubleshooting row that says `docker compose logs -f celery_worker` with `docker compose logs -f app`.

- [ ] **Step 3: Update the Service Ports table**

Change the `FastAPI Backend` row to note it is internal to the `app` container, and add the gateway note that it now shares that container. Keep the host ports (`3000`, `8899`) and the internal ports (`8000`, `8899`) accurate.

- [ ] **Step 4: Rewrite the Configuration section**

Replace the whole `## ⚙️ Configuration (Environment Variables)` code block with the contents of the new `.env.example` (Task 1, Step 7), and add a short **old → new** table directly after it:

```markdown
### Renamed variables (breaking change)

| Old | New |
| --- | --- |
| `SECRET_KEY` | `APP_KEY` |
| `ALGORITHM` | `JWT_ALGORITHM` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `JWT_ACCESS_TOKEN_TTL` |
| `DATABASE_URL` | `DB_URL` |
| `POSTGRES_USER` | `DB_USERNAME` |
| `POSTGRES_PASSWORD` | `DB_PASSWORD` |
| `POSTGRES_DB` | `DB_DATABASE` |
| `CELERY_BROKER_URL` | `QUEUE_BROKER_URL` |
| `CELERY_RESULT_BACKEND` | `QUEUE_RESULT_BACKEND` |
| `PORT` | `FRONTEND_PORT` |

`REDIS_URL` was removed (it was unused). `APP_PORT` was added for the API host port.
```

- [ ] **Step 5: Replace the Manual Local Development section**

Replace the manual 5-terminal instructions and the `start-dev.bat` tip with:

```markdown
## 💻 Manual Local Development

### Prerequisites
- [**Python**](https://www.python.org/downloads/) >= 3.10
- [**Node.js**](https://nodejs.org/) >= 18.x
- [**PostgreSQL**](https://www.postgresql.org/download/) >= 14 running locally (create a database, e.g. `proxyhub`)
- [**Redis**](https://redis.io/docs/getting-started/installation/) running at `localhost:6379`

### One-command setup (Linux, macOS, Windows)

```bash
python dev.py setup   # venv + pip install + .env files + npm install
python dev.py run     # API + frontend + gateway + Celery worker + beat
```

`dev.py run` starts all five processes in one terminal; `Ctrl+C` stops them all.
Create the first admin account with `python dev.py admin --username admin --email admin@example.com --password <password>`.

### Running services individually

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
celery -A app.worker.celery_app worker --loglevel=info   # Windows: add --pool=threads
celery -A app.worker.celery_app beat --loglevel=info
python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 127.0.0.1 --port 8899
cd frontend && npm run dev
```
```

- [ ] **Step 6: Fix the remaining stale references**

Search the README for `backend`, `celery_worker`, `celery_beat`, `gateway` (as service names), `DATABASE_URL`, `SECRET_KEY`, `CELERY_`, `POSTGRES_`, and `start-dev.bat`; update each to the new name or remove it. In the SQLite→Postgres migration section, change `DATABASE_URL` to `DB_URL`. In Security Notes, change `SECRET_KEY` to `APP_KEY`.

Run: `grep -n "start-dev.bat\|celery_worker\|celery_beat\|DATABASE_URL\|SECRET_KEY\|CELERY_\|POSTGRES_" README.md`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: document 4-service compose, dev.py bootstrap, and renamed env vars"
```

---

### Task 6: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Backend lint and tests**

Run: `ruff check app/ tests/ scripts/`
Expected: `All checks passed!`

Run: `pytest --cov=app --cov-report=term -q`
Expected: all tests pass, coverage at or above the pre-change level (~90%).

- [ ] **Step 2: Frontend lint, build, and tests**

Run: `cd frontend && npm run lint && npm run build && npm test`
Expected: lint 0 warnings; build succeeds; all tests pass.

- [ ] **Step 3: Compose sanity**

Run: `docker compose config --services`
Expected: `redis`, `postgres`, `app`, `frontend`.

- [ ] **Step 4: Confirm the spec's file list is complete**

Re-read `docs/superpowers/specs/2026-10-01-setup-simplification-design.md` §9 and confirm every listed file was changed. Report any that were not.

- [ ] **Step 5: Push and watch CI**

```bash
git push origin main
```
Expected: the `backend` and `frontend` CI jobs pass.

## Self-Review

**Spec coverage:** §5 rename map → Task 1; §8 `/healthz` → Task 2; §6 Compose 7→4 + §9 Dockerfile/frontend/nginx → Task 3; §7 `dev.py` → Task 4; §9 README → Task 5; §11 verification → Task 6. §4 invariant is enforced by Global Constraints and checked by the DB-key test that already exists (`tests/test_settings_api.py`, `tests/test_worker.py` assert on the key strings) plus the Step 6 grep in Task 1.

**Placeholder scan:** no TBD/TODO; every code step carries the actual content.

**Type consistency:** `Settings` fields (`DB_URL`, `APP_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_TTL`, `QUEUE_BROKER_URL`, `QUEUE_RESULT_BACKEND`) are used identically in Tasks 1, 3, and 4; `/healthz` is produced in Task 2 and consumed in Task 3; service name `app` is produced in Task 3 and consumed by `frontend/nginx.conf` and the README in Tasks 3 and 5.
