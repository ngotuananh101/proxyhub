# ProxyHub images, all from this file and the repository root as context:
#
#   docker build -t proxyhub .                        # allinone (default target)
#   docker build --target backend -t proxyhub-api .   # API + worker + beat + gateway
#
# `backend` is the split image docker-compose.yml runs; the React dashboard is
# built separately from frontend/Dockerfile there and served by Nginx.
#
# `allinone` (the default, and what .github/workflows/docker.yml publishes)
# ships both halves in one container behind a single port: FastAPI serves the
# compiled dashboard itself (app/core/spa.py) and answers on 8000, with no
# reverse proxy between the browser and the API.

# Stage 1: compile the React dashboard.
FROM node:24-alpine AS dashboard-build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
# No `|| npm install` fallback: a lockfile out of sync with package.json should
# fail the build, not silently resolve a different dependency tree.
RUN npm ci

COPY frontend/ .

# Vite reads these at build time. Empty means same-origin, which is what the
# combined image wants: the API serves the bundle, so /api and /ws are on the
# same origin as the page.
ARG VITE_API_URL=""
ARG VITE_WS_URL=""
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build


# Stage 2: the API, Celery worker and beat, and the proxy gateway, all under
# supervisor (see deploy/supervisor.conf).
FROM python:3.14-slim AS backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Build dependencies live only in this layer: psycopg/cryptography need a
# compiler to build, but the runtime image does not. Removing them afterwards
# keeps the image (and its CVE surface) small.
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application source code
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/
COPY scripts/ ./scripts/

# One container runs api + worker + beat + gateway under supervisor. Installed
# at supervisor's own default path so `docker exec <ctr> supervisorctl status`
# works without repeating -c; the CMD passes it explicitly anyway.
COPY deploy/supervisor.conf /etc/supervisord.conf

# Run unprivileged. The app writes SQLite (in the default dev config) and
# celery beat's schedule file into /app, so that tree must be owned by the user.
# /app/data is created up front so `DB_DATABASE=/app/data/...` works with a
# volume mounted there instead of failing to open a missing directory.
RUN useradd --system --uid 1000 --create-home proxyhub \
    && mkdir -p /app/data \
    && chown -R proxyhub:proxyhub /app

USER proxyhub

EXPOSE 8000 8899

CMD ["supervisord", "-c", "/etc/supervisord.conf"]


# Stage 3 (default): the whole application in one image. The bundle goes to
# /app/frontend/dist, which the API serves when FRONTEND_DIST points at it; the
# same supervisord programs run, with no Nginx in front.
FROM backend AS allinone

COPY --from=dashboard-build --chown=proxyhub:proxyhub /app/dist ./frontend/dist

ENV FRONTEND_DIST=/app/frontend/dist

# The dashboard and the API share 8000; 8899 stays the proxy gateway.
EXPOSE 8000 8899
