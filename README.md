# 🔄 ProxyHub: Smart Proxy Management & Rotation System

> ✅ **Status:** MVP & Docker Compose complete — includes the full Backend (FastAPI), Frontend Dashboard (React), Proxy Gateway (`proxy.py`), Background Health Checks (Celery + Redis), and full Docker Compose orchestration. Further features are being developed according to the [Roadmap](#️-roadmap).

ProxyHub is an open-source full-stack application for managing, health-checking, and automatically rotating a pool of proxies. It provides an intuitive Dashboard for managing the proxy pool and a high-performance API Gateway for forwarding traffic.

## 📸 Screenshots

<p align="center">
  <img src="screenshot/proxy-page.png" alt="Proxies Management" width="100%">
  <em>Proxies management dashboard with real-time health metrics, status filtering, and bulk operations</em>
</p>

<details>
<summary><b>🖼️ View More Screenshots (Sources, Live Logs, Settings, Profile & Login)</b></summary>
<br>

### 📥 Auto Proxy Sources
![Proxy Sources](screenshot/source-page.png)

### 📊 Real-time Request Logs Feed
![Request Logs](screenshot/logs-page.png)

### ⚙️ Runtime Settings & Health Check Configuration
![Settings](screenshot/setting-page.png)

### 👤 Profile & Password Management
![Profile](screenshot/profile-page.png)

### 🔐 Authentication
![Login](screenshot/login-page.png)

</details>

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [🏗️ System Architecture](#️-system-architecture)
- [🛠️ Tech Stack](#️-tech-stack)
- [🐳 Quick Start with Docker Compose (Recommended)](#-quick-start-with-docker-compose-recommended)
- [💻 Manual Local Development](#-manual-local-development)
- [⚙️ Configuration](#️-configuration-environment-variables)
- [👤 Creating the First Account](#-creating-the-first-account)
- [📖 Usage](#-usage)
- [🧠 Proxy Rotation Logic](#-proxy-rotation-logic-gateway-plugin)
- [🗄️ Migrating from SQLite to PostgreSQL](#️-migrating-from-sqlite-to-postgresql)
- [🔒 Security Notes](#-security-notes)
- [🩹 Troubleshooting](#-troubleshooting)
- [🗺️ Roadmap](#️-roadmap)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

## ✨ Key Features

Target features of the project:

- **🎯 Dynamic rotation gateway:** Uses **`proxy.py`** as the Gateway, automatically picking a live proxy from the pool for each request.
- **🩺 Automatic health checks:** Integrates **`Celery`** running in the background to periodically check the latency and success rate of each proxy.
- **📥 Automatic proxy sources:** Imports proxies from free proxy list feeds (plain-text URLs) on a per-source schedule — configurable from the Dashboard.
- **📊 Comprehensive dashboard:** A **`React`** UI for managing proxies, viewing statistics, and request logs in real time.
- **🗂️ Pool/group management:** Group proxies by country, ISP, or custom tags.
- **🐘 PostgreSQL database:** Concurrent-safe storage (no write locks between the API and workers); SQLite is still supported for single-process setups.
- **🔒 Authentication & security:** JWT login, API token management for clients.
- **🐳 One-command deployment:** Full **`Docker Compose`** setup orchestrating frontend, backend, worker, beat, gateway, postgres, and redis.

## 🏗️ System Architecture

```mermaid
flowchart LR
    C[Client / Scraper] -->|HTTP/S Request| G[proxy.py Gateway<br/>:8899]
    G -->|Forward traffic| T[Target Website]
    G -->|Get alive proxy| B[FastAPI Backend<br/>:8000]

    R[React Dashboard<br/>:3000 / :5173] -->|Nginx Reverse Proxy / REST / WS| B
    B -->|CRUD / Logs| D[(PostgreSQL)]

    CB[Celery Beat] -->|Tick every 60s| CW[Celery Worker]
    CW -->|Test Proxy| P[Proxy Pool]
    CW -->|Update status / latency| D
    CW --> BR[(Redis)]
    B --> BR
    CB --> BR
```

### Service Ports

| Service              | Host Port | Internal Container Port | Notes                                           |
| -------------------- | --------- | ----------------------- | ----------------------------------------------- |
| Frontend Dashboard   | 3000      | 80 (Nginx)              | React SPA + Nginx Reverse Proxy for API & WS    |
| FastAPI Backend      | Internal  | 8000                    | Proxied via Nginx at `/api`, `/docs`            |
| proxy.py Gateway     | 8899      | 8899                    | Rotating proxy port for scrapers/clients        |
| PostgreSQL           | Internal  | 5432                    | Primary database (persistent volume)            |
| Redis                | Internal  | 6379                    | Broker/backend for Celery                       |

---

## 🐳 Quick Start with Docker Compose (Recommended)

Docker Compose runs all 7 services (`frontend`, `backend`, `celery_worker`, `celery_beat`, `gateway`, `postgres`, `redis`) with persistent volumes in a single command.

### 1. Clone repository & create `.env`

```bash
git clone https://github.com/ngotuananh101/proxyhub.git
cd proxyhub
cp .env.example .env
```

Edit `.env` to set your own secure secrets:
```env
SECRET_KEY=your_generated_secret_key
INTERNAL_API_KEY=your_internal_gateway_key
```

### 2. Start all services

```bash
docker compose up -d --build
```

### 3. Create your initial Admin account

```bash
docker compose run --rm backend python -m app.cli create-admin --username admin --email admin@example.com --password YourStrongPassword
```

### 4. Access ProxyHub

- **Dashboard & API:** Open **`http://localhost:3000`** in your browser and log in with your admin credentials.
- **API Documentation:** **`http://localhost:3000/docs`**
- **Rotating Proxy Gateway:** Connect scraping clients to **`http://localhost:8899`**.

### Useful Docker Compose commands

- **View live logs:** `docker compose logs -f`
- **View specific service logs:** `docker compose logs -f gateway` or `docker compose logs -f celery_worker`
- **Restart services:** `docker compose restart`
- **Stop all services:** `docker compose down`
- **Stop and remove volumes:** `docker compose down -v`

---

## 💻 Manual Local Development

If you prefer developing without Docker:

### Prerequisites
- [**Python**](https://www.python.org/downloads/) >= 3.10
- [**Node.js**](https://nodejs.org/) >= 18.x
- [**PostgreSQL**](https://www.postgresql.org/download/) >= 14 running locally (create a database, e.g. `proxyhub`)
- [**Redis**](https://redis.io/docs/getting-started/installation/) running at `localhost:6379`

### 1. Backend Setup

```bash
python -m venv venv
# Linux/macOS: source venv/bin/activate
# Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Run API Server:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run Celery Worker:
```bash
# Linux/macOS:
celery -A app.worker.celery_app worker --loglevel=info
# Windows:
celery -A app.worker.celery_app worker --loglevel=info --pool=threads --concurrency=8
```

Run Celery Beat:
```bash
celery -A app.worker.celery_app beat --loglevel=info
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
Dashboard runs at `http://localhost:5173`.

### 3. Gateway Setup

```bash
python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin --hostname 127.0.0.1 --port 8899
```

> 💡 **Tip:** Run `start-dev.bat` on Windows to launch all 5 dev services in a single terminal with `npx concurrently`.

---

## ⚙️ Configuration (Environment Variables)

The **`.env`** file contains configuration values:

```env
# Database (PostgreSQL)
# Local: postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/proxyhub
# Docker Compose: postgresql+psycopg://proxyhub:proxyhub@postgres:5432/proxyhub (auto-configured in docker-compose.yml)
# SQLite still works for single-process setups: sqlite:///./proxyhub.db
DATABASE_URL=postgresql+psycopg://proxyhub:proxyhub@127.0.0.1:5432/proxyhub

# Redis (for Celery)
REDIS_URL=redis://127.0.0.1:6379/0

# JWT Auth
SECRET_KEY=your_super_secret_key_change_me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Internal Gateway Security Key
INTERNAL_API_KEY=change_me_internal_key

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

# CORS Configuration
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost

# Docker Port Mappings (Optional overrides)
PORT=3000
GATEWAY_PORT=8899
```

---

## 👤 Creating the First Account

In Docker:
```bash
docker compose run --rm backend python -m app.cli create-admin --username admin --email admin@example.com --password <your-password>
```

In Local Dev:
```bash
python -m app.cli create-admin --username admin --email admin@example.com --password <your-password>
```

---

## 📖 Usage

### 1. Add Proxies to the Pool

Go to Dashboard → **`Proxies`** → **`Import`**.

Supports pasting text in the form:

```text
http://user:pass@1.2.3.4:8080
socks5://5.6.7.8:1080
```

### 2. Configure your software

Point your scraping/automation software at the Gateway. ProxyHub automatically rotates the IP for each request:

```bash
curl -x http://localhost:8899 http://httpbin.org/ip
```

The response will be the IP of a proxy from the pool, and it will change on the next request.

### 3. Health Check

The Celery worker automatically checks all proxies in the database periodically via the health check URL. The default cycle is **every 5 minutes**, and the cycle parameters — URL, timeout, interval, and concurrency (`HEALTH_CHECK_URL`, `HEALTH_CHECK_TIMEOUT`, `HEALTH_CHECK_INTERVAL`, `HEALTH_CHECK_CONCURRENCY`) — can be changed at any time from the Dashboard → **`Settings`** page without editing `.env` or restarting any service.

Only proxies in the `alive` or `unknown` state are checked — `dead` proxies are skipped to save time (re-importing a dead proxy transitions it back to `unknown` for re-verification).

Besides the automatic cycle, you can trigger a manual check at any time:
- Click the **"Check now"** button on the React Dashboard (Proxy list page).
- Or call the API: `POST /api/proxies/check-all`.

### 4. Automatic Proxy Sources

Go to Dashboard → **`Sources`** to manage free proxy list feeds. Each source is a plain-text URL with its own update interval in minutes. The Celery worker fetches every enabled source when its interval elapses and imports new proxies.

- **"Fetch now"** button forces an immediate fetch of one source.
- Proxies that have been `dead` for longer than the retention period (Settings → *Dead proxy retention*, default 7 days) are removed automatically on each source fetch.

### 5. Realtime Dashboard & Request Logs

The Dashboard updates live over a WebSocket (`/ws/events`, authenticated with your JWT):

- **Stats refresh automatically** — proxy counts on the Proxies page update in real time.
- **Request logs stream in live** — every request that passes through the Gateway is pushed to the Backend (`POST /internal/logs`) and appears instantly on the **`Logs`** page.

---

## 🧠 Proxy Rotation Logic (Gateway Plugin)

The **`RotateProxyPlugin`** plugin extends `proxy.py`'s **`HttpProxyBasePlugin`**. For each incoming request:

1. The plugin calls the FastAPI internal API **`GET /internal/proxies?strategy=random`** (with the `X-Internal-Key` header).
2. FastAPI queries the database for an **`alive`** proxy and returns its URL.
3. The plugin establishes the upstream connection to that proxy.
4. Traffic is forwarded along the path **client → upstream proxy → target**.

---

## 🗄️ Migrating from SQLite to PostgreSQL

If you have an existing `proxyhub.db` from a previous SQLite setup, a one-shot script copies all data (users, settings, proxies, sources, request logs) into PostgreSQL:

1. Stop the app so the SQLite file is not being written to.
2. Point `DATABASE_URL` in `.env` at your PostgreSQL database.
3. Run the migration:

```bash
# Local dev
python -m scripts.migrate_sqlite_to_postgres ./proxyhub.db

# Docker Compose (copy proxyhub.db next to docker-compose.yml first)
docker compose run --rm -v $(pwd)/proxyhub.db:/tmp/proxyhub.db \
  backend python -m scripts.migrate_sqlite_to_postgres /tmp/proxyhub.db
```

The script is idempotent — tables that already contain rows are skipped, so it is safe to re-run. The original `proxyhub.db` is only read, never modified; you can switch back at any time by setting `DATABASE_URL` to the SQLite path.

---

## 🔒 Security Notes

- **Bind to localhost during development:** In local dev, bind to `127.0.0.1`. In Docker, only expose necessary host ports (`PORT:80` and `GATEWAY_PORT:8899`).
- **Internal API key:** The `/internal/proxies` endpoint returns proxy URLs including credentials, protected by `INTERNAL_API_KEY` (`X-Internal-Key`).
- **Change `SECRET_KEY`:** Always generate a random `SECRET_KEY`; never use the default value in production.

---

## 🩹 Troubleshooting

| Problem                                       | Cause / Fix                                                                                                                  |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Celery worker crashes on Windows              | Celery does not support Windows with the default pool. Use Docker Compose (recommended) or `--pool=threads`.               |
| `ConnectionError: redis://127.0.0.1:6379`     | Redis is not running. Start Redis (`redis-server`) or verify container `proxyhub-redis` is running.                         |
| `OperationalError: connection refused` (Postgres) | PostgreSQL is not running or `DATABASE_URL` is wrong. In Docker, verify container `proxyhub-postgres` is healthy.      |
| Port 3000 or 8899 already in use              | Port conflict on host. Change `PORT` or `GATEWAY_PORT` in `.env`.                                                           |
| `database is locked` (SQLite only)            | Only relevant if you kept SQLite. FastAPI and Celery write concurrently; WAL mode and `busy_timeout` are enabled by default. Switching to PostgreSQL removes this class of error. |
| Gateway errors but Dashboard still shows proxies alive | Health check hasn't completed a cycle yet. Check worker logs (`docker compose logs -f celery_worker`) or click "Check now". |

---

## 🗺️ Roadmap

- [x] MVP: Proxy CRUD, Manual Rotate, SQLite
- [x] Automatic Celery Health Check
- [x] Automatic Proxy Source Feeds & Dead Retention Purge
- [x] WebSocket Realtime Logs & Stats
- [x] Docker Compose: One-command deployment (`docker compose up -d`)
- [x] PostgreSQL backend with SQLite → PostgreSQL migration script
- [ ] Multi-tenant: Assign Users/API Keys to separate Pools
- [ ] Sticky Session: Keep the same IP for a `session_id` for N minutes

---

## 🤝 Contributing

All pull requests are welcome! For significant changes, please open an issue first to discuss the direction.

---

## 📄 License

Distributed under the MIT License. See the **`LICENSE`** file for details.
