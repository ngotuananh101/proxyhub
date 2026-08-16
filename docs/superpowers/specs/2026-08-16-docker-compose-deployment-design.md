# Docker Compose Deployment Design for ProxyHub

## 1. Overview
ProxyHub is a full-stack proxy pool manager and rotating gateway consisting of:
- **Backend API**: FastAPI application (Python 3.12, SQLModel/SQLite, WebSockets, JWT auth).
- **Frontend Dashboard**: React 19 SPA (Vite, TailwindCSS v4, shadcn base-sera UI, Nginx reverse proxy).
- **Proxy Gateway**: `proxy.py` HTTP proxy service with `RotateProxyPlugin` querying the backend internal API.
- **Task Worker**: Celery worker running health-checks and proxy source ingestion.
- **Task Scheduler**: Celery beat scheduling periodic health checks and source syncing.
- **Redis**: In-memory broker and result backend for Celery.
- **Persistent Data**: SQLite WAL database mounted to shared volume and Redis persistence.

## 2. Architecture & Container Specifications

### 2.1 Backend / Worker / Gateway / Beat Base Image (`Dockerfile`)
- **Base**: `python:3.12-slim`
- **Working Directory**: `/app`
- **Dependencies**: `requirements.txt`
- **Source Code**: `app/` and optional CLI scripts.
- **Volume Mount Point**: `/app/data` for `proxyhub.db`.

### 2.2 Frontend Image (`frontend/Dockerfile` & `frontend/nginx.conf`)
- **Stage 1 (Builder)**: `node:20-alpine`, `npm install`, `npm run build`.
- **Stage 2 (Runtime)**: `nginx:alpine`
- **Routing & Proxy Rules**:
  - `/` -> SPA static files (`/usr/share/nginx/html`), fallback to `index.html`.
  - `/api/`, `/internal/`, `/docs`, `/openapi.json` -> Reverse proxy to `http://backend:8000`.
  - `/ws/` -> Reverse proxy to `http://backend:8000` with WebSocket upgrade headers (`Upgrade`, `Connection`).

### 2.3 Docker Compose Services (`docker-compose.yml`)
1. **`redis`**:
   - Image: `redis:7-alpine`
   - Volumes: `redis_data:/data`
   - Command: `redis-server --appendonly yes`
2. **`backend`**:
   - Build: `.` (Dockerfile)
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Volumes: `app_data:/app/data`
   - Env vars: `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `SECRET_KEY`, `INTERNAL_API_KEY`, `CORS_ORIGINS`.
   - Depends on: `redis`.
3. **`celery_worker`**:
   - Build: `.` (Dockerfile)
   - Command: `celery -A app.worker.celery_app worker --loglevel=info -c 4`
   - Volumes: `app_data:/app/data`
   - Depends on: `redis`, `backend`.
4. **`celery_beat`**:
   - Build: `.` (Dockerfile)
   - Command: `celery -A app.worker.celery_app beat --loglevel=info`
   - Volumes: `app_data:/app/data`
   - Depends on: `redis`, `backend`.
5. **`gateway`**:
   - Build: `.` (Dockerfile)
   - Command: `proxy --hostname 0.0.0.0 --port 8899 --plugins app.gateway.plugin.RotateProxyPlugin`
   - Ports: `8899:8899`
   - Env vars: `GATEWAY_API_URL`, `GATEWAY_LOG_URL`, `INTERNAL_API_KEY`.
   - Depends on: `backend`.
6. **`frontend`**:
   - Build: `./frontend` (`frontend/Dockerfile`)
   - Ports: `3000:80` (Configurable via `PORT`)
   - Depends on: `backend`.

## 3. Environment & Configuration (.env.example)
- Update `.env.example` with Docker-friendly defaults and explanatory comments.
- Shared environment variables via `.env` file passed to compose services.

## 4. Documentation & Operations (README.md)
- Deployment instructions using Docker Compose (`docker compose up -d --build`).
- Creating initial admin user via CLI container (`docker compose run --rm backend python -m app.cli create-admin ...`).
- Viewing logs, stopping/restarting services, managing persistent data.
- Connecting to rotating proxy gateway (`http://<server-ip>:8899`).
