# Docker Compose Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete, production-ready Docker Compose deployment configuration for ProxyHub (FastAPI backend, Celery worker & beat, Redis, proxy.py gateway, and Nginx-based React frontend) and update project documentation.

**Architecture:** 
- Shared multi-purpose Python base container (`Dockerfile`) for `backend`, `celery_worker`, `celery_beat`, and `gateway` with shared SQLite database volume at `/app/data`.
- Multi-stage Node/Nginx container (`frontend/Dockerfile` + `frontend/nginx.conf`) serving the React SPA and acting as reverse proxy for `/api`, `/internal`, `/ws`, `/docs`, and `/openapi.json`.
- Unified `docker-compose.yml` orchestrating all 6 services with health-checks, volume mounts, and network configuration.

**Tech Stack:** Docker, Docker Compose, Nginx Alpine, Python 3.12-slim, Node.js 20-alpine, Vite, FastAPI, Celery, Redis 7.

## Global Constraints

- Never commit `.env` or sensitive secrets (`SECRET_KEY`, `INTERNAL_API_KEY`) to Git.
- Maintain SQLite WAL mode with persistent volume storage (`/app/data/proxyhub.db`).
- Proxy Gateway runs via `python -m proxy` with `RotateProxyPlugin` listening on `0.0.0.0:8899`.
- Frontend SPA supports relative URL fallback for API and WebSockets through Nginx reverse proxy.
- Admin creation command runs via `docker compose run --rm backend python -m app.cli create-admin ...`.

---

### Task 1: Frontend Dynamic URL Resolution & Nginx Configuration

**Files:**
- Modify: `frontend/src/api/client.ts:1-27`
- Modify: `frontend/src/hooks/useRealtime.ts:29-55`
- Create: `frontend/nginx.conf`
- Create: `frontend/.dockerignore`
- Create: `frontend/Dockerfile`

**Interfaces:**
- `client.ts`: Uses `import.meta.env.VITE_API_URL || ''` so API calls seamlessly default to relative paths when served behind Nginx.
- `useRealtime.ts`: Uses `import.meta.env.VITE_WS_URL || window.location default` to support WebSocket proxying through Nginx `/ws/events`.
- `nginx.conf`: Proxies `/api/`, `/internal/`, `/docs`, `/openapi.json`, and `/ws/` to `http://backend:8000`.

- [ ] **Step 1: Update `frontend/src/api/client.ts` to support relative base URL**

Modify `frontend/src/api/client.ts` so `baseURL` defaults to `import.meta.env.VITE_API_URL ?? ''` (relative URL for Nginx reverse proxy):

```typescript
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
```

- [ ] **Step 2: Update `frontend/src/hooks/useRealtime.ts` for dynamic WebSocket URL fallback**

Modify `frontend/src/hooks/useRealtime.ts` lines 29-37:

```typescript
function getWsUrl(token: string): string {
  const customWsUrl = import.meta.env.VITE_WS_URL
  if (customWsUrl) {
    return `${customWsUrl}/ws/events?token=${encodeURIComponent(token)}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`
}

function connect() {
  const token = localStorage.getItem('access_token')
  if (!token) return

  const url = getWsUrl(token)

  socket = new WebSocket(url)
  socket.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data) as RealtimeEvent
      listeners.forEach((listener) => listener(event))
    } catch {
      // ignore malformed frames
    }
  }
  socket.onopen = () => {
    retry = 0
  }
  socket.onclose = () => {
    socket = null
    if (listeners.size === 0) return
    const delay = Math.min(1000 * 2 ** retry, 15000)
    retry += 1
    retryTimer = setTimeout(connect, delay)
  }
}
```

- [ ] **Step 3: Create `frontend/nginx.conf`**

Create `frontend/nginx.conf` with reverse proxy rules and WebSocket support:

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html index.htm;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Frontend SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API & Documentation proxy
    location ~ ^/(api|internal|docs|openapi\.json) {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

- [ ] **Step 4: Create `frontend/.dockerignore` and `frontend/Dockerfile`**

Create `frontend/.dockerignore`:
```text
node_modules
dist
.env
.env.local
.git
npm-debug.log*
```

Create `frontend/Dockerfile`:
```dockerfile
# Stage 1: Build the React application
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 5: Verify frontend tests & build**

Run: `npm test && npm run build` inside `frontend/` directory
Expected: All tests pass, build completes without errors.

---

### Task 2: Root Dockerfile & Dockerignore for Backend / Worker / Gateway

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Base image: `python:3.12-slim`
- Sets `PYTHONPATH=/app` and creates `/app/data`
- Can be invoked with different commands:
  - Backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - Worker: `celery -A app.worker.celery_app worker --loglevel=info`
  - Beat: `celery -A app.worker.celery_app beat --loglevel=info`
  - Gateway: `python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 0.0.0.0 --port 8899`
  - CLI: `python -m app.cli <args>`

- [ ] **Step 1: Create `.dockerignore`**

Create `.dockerignore`:
```text
.git
.gitignore
venv
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.coverage
htmlcov
proxyhub.db*
data
frontend
node_modules
.env
.env.local
.claude
tests
docs
*.log
```

- [ ] **Step 2: Create root `Dockerfile`**

Create `Dockerfile`:
```dockerfile
FROM python:3.12-slim

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
COPY app/ ./app/

# Create data directory for SQLite database storage
RUN mkdir -p /app/data

EXPOSE 8000 8899

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Run backend test suite to verify everything remains green**

Run: `pytest`
Expected: All backend unit tests pass.

---

### Task 3: Compose Configuration (`docker-compose.yml` & `.env.example`)

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- `docker-compose.yml`: Defines 6 services (`redis`, `backend`, `celery_worker`, `celery_beat`, `gateway`, `frontend`), 2 volumes (`app_data`, `redis_data`), and default bridge network.
- `.env.example`: Documents environment variables for both Docker Compose and Local Development modes.

- [ ] **Step 1: Create `docker-compose.yml`**

Create `docker-compose.yml`:
```yaml
services:
  redis:
    image: redis:7-alpine
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

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proxyhub-backend
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite:////app/data/proxyhub.db
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    volumes:
      - app_data:/app/data
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - proxyhub-network

  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proxyhub-worker
    restart: unless-stopped
    command: celery -A app.worker.celery_app worker --loglevel=info
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite:////app/data/proxyhub.db
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    volumes:
      - app_data:/app/data
    depends_on:
      redis:
        condition: service_healthy
      backend:
        condition: service_started
    networks:
      - proxyhub-network

  celery_beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proxyhub-beat
    restart: unless-stopped
    command: celery -A app.worker.celery_app beat --loglevel=info
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite:////app/data/proxyhub.db
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    volumes:
      - app_data:/app/data
    depends_on:
      redis:
        condition: service_healthy
      backend:
        condition: service_started
    networks:
      - proxyhub-network

  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proxyhub-gateway
    restart: unless-stopped
    command: python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 0.0.0.0 --port 8899
    env_file:
      - .env
    environment:
      - GATEWAY_API_URL=http://backend:8000/internal/proxies
      - GATEWAY_LOG_URL=http://backend:8000/internal/logs
    ports:
      - "${GATEWAY_PORT:-8899}:8899"
    depends_on:
      - backend
    networks:
      - proxyhub-network

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: proxyhub-frontend
    restart: unless-stopped
    ports:
      - "${PORT:-3000}:80"
    depends_on:
      - backend
    networks:
      - proxyhub-network

volumes:
  app_data:
  redis_data:

networks:
  proxyhub-network:
    driver: bridge
```

- [ ] **Step 2: Update `.env.example`**

Update `.env.example`:
```env
# ==========================================
# ProxyHub Environment Variables
# ==========================================

# Database
# Local: sqlite:///./proxyhub.db
# Docker Compose: sqlite:////app/data/proxyhub.db (auto-configured in docker-compose.yml)
DATABASE_URL=sqlite:///./proxyhub.db

# Redis (for Celery)
# Local: redis://127.0.0.1:6379/0
# Docker Compose: redis://redis:6379/0
REDIS_URL=redis://127.0.0.1:6379/0

# JWT Auth
SECRET_KEY=change_me_to_a_random_secure_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Internal Gateway Security Key
# Must match between Backend and Gateway
INTERNAL_API_KEY=change_me_to_a_random_internal_api_key

# Celery Configuration
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2

# Health Check Settings (Seeded to database on first startup)
HEALTH_CHECK_URL=https://api.ipify.org
HEALTH_CHECK_TIMEOUT=6
HEALTH_CHECK_INTERVAL=300
HEALTH_CHECK_CONCURRENCY=50

# Gateway Configuration
GATEWAY_API_URL=http://localhost:8000/internal/proxies
GATEWAY_LOG_URL=http://localhost:8000/internal/logs

# CORS Configuration (Comma-separated origins)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost

# Docker Port Mappings (Optional overrides)
PORT=3000
GATEWAY_PORT=8899
```

---

### Task 4: Documentation Update (`README.md`)

**Files:**
- Modify: `README.md`

**Interfaces:**
- Comprehensive deployment guide covering Docker Compose quick start, admin user creation, logs monitoring, proxy usage, local development, and troubleshooting.
- Check off Docker Compose in Roadmap.

- [ ] **Step 1: Update `README.md`**

Update `README.md` with a dedicated **🐳 Docker Compose Deployment (Recommended)** section right at the top of Installation & Deployment, update system architecture table, and mark the Roadmap item as complete.

- [ ] **Step 2: Review all files & formatting**

Verify all Markdown links and code snippets in `README.md`.
