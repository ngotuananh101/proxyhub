# 🔄 ProxyHub: Smart Proxy Management & Rotation System

> ✅ **Status:** MVP complete — includes the full Backend (FastAPI), Frontend Dashboard (React), and Proxy Gateway (`proxy.py`). Further features are being developed according to the [Roadmap](#️-roadmap).

ProxyHub is an open-source full-stack application for managing, health-checking, and automatically rotating a pool of proxies. It provides an intuitive Dashboard for managing the proxy pool and a high-performance API Gateway for forwarding traffic.

## 📸 Screenshots

> _(To be added once the Dashboard is finalized)_

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [🏗️ System Architecture](#️-system-architecture)
- [🛠️ Tech Stack](#️-tech-stack)
- [📋 Prerequisites](#-prerequisites)
- [🚀 Installation & Development](#-installation--development)
- [⚙️ Configuration](#️-configuration-environment-variables)
- [👤 Creating the First Account](#-creating-the-first-account)
- [📖 Usage](#-usage)
- [🧠 Proxy Rotation Logic](#-proxy-rotation-logic-gateway-plugin)
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
- **⚡ Lightweight database:** Uses **`SQLite`** (read/write via WAL mode), no complex DB server setup required.
- **🔒 Authentication & security:** JWT login, API token management for clients.

> Actual progress of each feature is tracked in the [Roadmap](#️-roadmap) section.

## 🏗️ System Architecture

```mermaid
flowchart LR
    C[Client / Scraper] -->|HTTP/S Request| G[proxy.py Gateway<br/>:8899]
    G -->|Forward traffic| T[Target Website]
    G -->|Get alive proxy| B[FastAPI Backend<br/>:8000]

    R[React Dashboard<br/>:5173] -->|REST API / WebSocket| B
    B -->|CRUD / Logs| D[(SQLite DB)]

    CB[Celery Beat] -->|Tick every 60s| CW[Celery Worker]
    CW -->|Test Proxy| P[Proxy Pool]
    CW -->|Update status / latency| D
    CW --> BR[(Redis)]
    B --> BR
    CB --> BR
```

### Service Ports

| Service              | Port  | Notes                                      |
| -------------------- | ----- | ------------------------------------------ |
| FastAPI Backend      | 8000  | REST API + Swagger docs at `/docs`         |
| React Dashboard      | 5173  | Vite dev server                            |
| proxy.py Gateway     | 8899  | Proxy port for clients to connect to       |
| Redis                | 6379  | Broker/backend for Celery                  |

### Main Flow

1. The Client/Scraper sends a request to the **`proxy.py Gateway :8899`**.
2. The Gateway calls the **FastAPI Backend :8000** to get a working proxy.
3. The Gateway forwards traffic to the **Target Website** through the selected proxy.
4. The **React Dashboard :5173** communicates with the Backend via REST API/WebSocket.
5. **Celery Beat** periodically triggers the **Celery Worker** to check proxies.
6. The Worker updates status, latency, and health check info into **SQLite**.
7. **Redis** is used as the broker/backend for Celery tasks.

## 🛠️ Tech Stack

| Component       | Technology                         | Description                              |
| --------------- | ---------------------------------- | ---------------------------------------- |
| **Frontend**    | React, Vite, TailwindCSS, ShadcnUI | Fast, modern management UI               |
| **Backend API** | FastAPI, SQLModel, Pydantic        | High-performance REST API, auto docs     |
| **Gateway**     | proxy.py                           | Forward proxy server with custom plugin  |
| **Task Queue**  | Celery, Redis                      | Background health check jobs             |
| **Database**    | SQLite (WAL mode)                  | Stores proxies, logs, users              |

## 📋 Prerequisites

Before starting, make sure your machine has:

- [**Python**](https://www.python.org/downloads/) >= 3.10
- [**Node.js**](https://nodejs.org/) >= 18.x
- [**Redis**](https://redis.io/docs/getting-started/installation/) (used as the message broker for Celery)

> ⚠️ **Windows note:** Celery is **not officially supported on Windows**. When running worker/beat on Windows, an alternative pool is required (`--pool=solo` or `--pool=threads`) — see the Celery run instructions below. The most stable option is to run via **WSL2** or **Docker**.

## 🚀 Installation & Development

### 1. Clone the repository

```bash
git clone https://github.com/ngotuananh101/proxyhub.git
cd proxyhub
```

### 2. Backend Setup (FastAPI + Celery)

#### Create and activate a virtual environment

**Linux/macOS:**

```bash
python -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Install dependencies

```bash
pip install -r requirements.txt
```

#### Create the config file

```bash
cp .env.example .env
```

> On Windows you can use `copy .env.example .env` in Command Prompt. See the [Configuration](#️-configuration-environment-variables) section for the environment variables.

#### Run the API Server (Terminal 1)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API Docs available at: **`http://localhost:8000/docs`**

> During development you should only bind `127.0.0.1`. Only use `0.0.0.0` when you understand the risks and have configured a firewall — see [Security Notes](#-security-notes).

#### Run the Celery Worker (Terminal 2)

Make sure Redis is running at `localhost:6379`.

**Linux/macOS:**

```bash
celery -A app.worker.celery_app worker --loglevel=info
```

**Windows** (Celery is not officially supported, a pool must be specified):

```bash
celery -A app.worker.celery_app worker --loglevel=info --pool=threads --concurrency=8
```

#### Run the Celery Beat Scheduler (Terminal 3)

```bash
celery -A app.worker.celery_app beat --loglevel=info
```

### 3. Frontend Setup (React)

```bash
cd frontend
npm install
cp .env.example .env
```

The frontend `.env` needs at minimum the variable pointing to the Backend:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

#### Run the Dashboard (Terminal 4)

```bash
npm run dev
```

Dashboard available at: **`http://localhost:5173`**

### 4. Run the Proxy Gateway (proxy.py)

The Gateway uses a custom plugin to call the API for a proxy and forward traffic.

> 💡 **Quick-start the whole system:** instead of opening each terminal, run `start-dev.bat` in the project root — the script uses `npx concurrently` to run the Backend, Frontend, Gateway, Celery Worker, and Celery Beat (with environment variables) in **a single window**, with color-coded logs per process. Press `Ctrl+C` to stop everything.

#### Run the Gateway (Terminal 5)

The plugin reads `GATEWAY_API_URL` and `INTERNAL_API_KEY` directly from environment variables (it does not read the `.env` file), so they must be passed when running. `INTERNAL_API_KEY` must **match** the value in the Backend's `.env`.

**Git Bash / Linux / macOS:**

```bash
GATEWAY_API_URL=http://localhost:8000/internal/proxies \
INTERNAL_API_KEY=<key-from-.env> \
python -m proxy --plugins app.gateway.plugin.RotateProxyPlugin \
    --hostname 127.0.0.1 \
    --port 8899
```

> ⚠️ Use `python -m proxy` (inside the venv) instead of the `proxy` command: the `proxy.exe` console script does not add the current directory to `sys.path`, so it fails with `... is not resolvable as a plugin class`.

## ⚙️ Configuration (Environment Variables)

The **`.env`** file in the project root contains the following variables:

```env
# Database
DATABASE_URL=sqlite:///./proxyhub.db

# Redis (for Celery)
REDIS_URL=redis://127.0.0.1:6379/0

# JWT Auth
SECRET_KEY=your_super_secret_key_change_me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Celery
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
HEALTH_CHECK_URL=https://api.ipify.org
# Timeout per check (seconds)
HEALTH_CHECK_TIMEOUT=6
# Automatic health check interval (seconds), default 300 = 5 minutes
HEALTH_CHECK_INTERVAL=300
# Number of proxies checked concurrently
HEALTH_CHECK_CONCURRENCY=50

# Gateway
GATEWAY_API_URL=http://localhost:8000/internal/proxies
# Where the gateway pushes request logs (defaults to <GATEWAY_API_URL minus last segment>/logs)
GATEWAY_LOG_URL=http://localhost:8000/internal/logs
# Internal key for the Gateway to authenticate against the Backend's internal API
INTERNAL_API_KEY=change_me_internal_key
```

> **Security note:** Never commit a `.env` file containing `SECRET_KEY` or other sensitive information to a Git repository.

## 👤 Creating the First Account

The Dashboard requires JWT login. After running the Backend for the first time, create an admin account via the CLI:

```bash
python -m app.cli create-admin --username admin --email admin@example.com --password <your-password>
```

Then sign in at **`http://localhost:5173`**.

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

The Celery worker automatically checks all proxies in the database periodically via the health check URL. The default cycle is **every 5 minutes**, and the cycle parameters — URL, timeout, interval, and concurrency (`HEALTH_CHECK_URL`, `HEALTH_CHECK_TIMEOUT`, `HEALTH_CHECK_INTERVAL`, `HEALTH_CHECK_CONCURRENCY`) — can be changed at any time from the Dashboard → **`Settings`** page without editing `.env` or restarting any service (values are seeded from `.env` on first startup, and the database value takes precedence afterwards). All proxies are checked **in parallel** within a single task — the number of concurrent checks is limited by the concurrency setting (default 50), and each check times out after the configured timeout (default 6 seconds). As a result, a cycle with a few hundred proxies takes only tens of seconds. Only proxies in the `alive` or `unknown` state are checked — `dead` proxies are skipped to save time (to re-check them, delete and re-import that proxy). Each proxy is marked `alive` or `dead` along with its response time `latency_ms` and the `last_checked_at` timestamp.

The Gateway only selects proxies in the `alive` state to forward traffic.

Besides the automatic cycle, you can trigger a manual check at any time:
- Click the **"Check now"** button on the React Dashboard (Proxy list page).
- Or call the API: `POST /api/proxies/check-all`.

### 4. Automatic Proxy Sources

Go to Dashboard → **`Sources`** to manage free proxy list feeds. Each source is a plain-text URL (one proxy per line, `ip:port` or `scheme://ip:port`) with its own update interval in minutes. The Celery worker fetches every enabled source when its interval elapses and imports new proxies — always in the `unknown` state, classified by the next health check cycle. Existing proxies are never touched, and duplicates are skipped. Two well-known lists are seeded on first startup; add or remove sources freely.

- **"Fetch now"** button forces an immediate fetch of one source.
- Proxies that have been `dead` for longer than the retention period (Settings → *Dead proxy retention*, default 7 days) are removed automatically on each source fetch.
- The download timeout is configurable in Settings → *Source fetch timeout*.

### 5. Realtime Dashboard & Request Logs

The Dashboard updates live over a WebSocket (`/ws/events`, authenticated with your JWT):

- **Stats refresh automatically** — when a health check cycle finishes, the proxy counts on the Proxies page update without a manual reload.
- **Request logs stream in live** — every request that passes through the Gateway is pushed to the Backend (`POST /internal/logs`) and appears instantly on the **`Logs`** page (client IP, method, host, path, the proxy used, and response size). The page also loads the most recent 100 entries from the database, so history survives restarts.

## 🧠 Proxy Rotation Logic (Gateway Plugin)

The **`RotateProxyPlugin`** plugin extends `proxy.py`'s **`HttpProxyBasePlugin`**. For each incoming request:

1. The plugin calls the FastAPI internal API **`GET /internal/proxies?strategy=random`** (with the `X-Internal-Key` header).
2. FastAPI queries SQLite to get an **`alive`** proxy and returns its URL.
3. The plugin establishes the upstream connection to that proxy.
4. Traffic is forwarded along the path **client → upstream proxy → target**.

> **Performance optimization:** FastAPI can cache the list of `alive` proxies in Redis and refresh it every 10 seconds, so the Gateway doesn't have to query the DB continuously.

## 🔒 Security Notes

- **Bind to localhost during development:** The Backend and Gateway should only listen on `127.0.0.1` by default. Only expose `0.0.0.0` when deploying behind a reverse proxy/firewall.
- **The internal API requires a key:** The `/internal/proxies` endpoint returns proxy URLs **including credentials (user:pass)**, so it must be authenticated with `INTERNAL_API_KEY` (header `X-Internal-Key`). Never expose this endpoint to the internet.
- **Change `SECRET_KEY`:** Always generate a random `SECRET_KEY`; never use the default value from `.env.example`.
- **Never commit `.env`:** Make sure `.env` is listed in `.gitignore`.

## 🩹 Troubleshooting

| Problem                                       | Cause / Fix                                                                                                                  |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Celery worker crashes on Windows              | Celery does not support Windows with the default pool. Add `--pool=threads --concurrency=8` (or `--pool=solo`); best to use WSL2/Docker. |
| `ConnectionError: redis://127.0.0.1:6379`     | Redis is not running. Start Redis (`redis-server`) or double-check `REDIS_URL`.                                              |
| Port 8899/8000 already in use                 | Port conflict with another application. Change the port with the `--port` flag or check which process holds the port.        |
| `database is locked` (SQLite)                 | FastAPI and the Celery worker writing concurrently. Make sure **WAL mode** is enabled and `busy_timeout` is set (default in the DB config). |
| Gateway errors but Dashboard still shows proxies alive | Health check hasn't completed a cycle yet. Check the Celery Beat/Worker logs, or trigger a manual health check from the Dashboard. |

## 🗺️ Roadmap

- [x] MVP: Proxy CRUD, Manual Rotate, SQLite
- [x] Automatic Celery Health Check
- [ ] Multi-tenant: Assign Users/API Keys to separate Pools
- [ ] Sticky Session: Keep the same IP for a `session_id` for N minutes
- [x] WebSocket Realtime Logs: View request logs live on the Dashboard
- [ ] Docker Compose: A single **`docker compose up`** command to run the whole system

## 🤝 Contributing

All pull requests are welcome! For significant changes, please open an issue first to discuss the direction.

## 📄 License

Distributed under the MIT License. See the **`LICENSE`** file for details.
