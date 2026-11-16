FROM python:3.14-slim

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

# One container runs api + worker + beat + gateway under supervisor.
COPY deploy/supervisor.conf /etc/supervisor/conf.d/proxyhub.conf

# Run unprivileged. The app writes SQLite (in the default dev config) and
# celery beat's schedule file into /app, so that tree must be owned by the user.
RUN useradd --system --uid 1000 --create-home proxyhub \
    && chown -R proxyhub:proxyhub /app

USER proxyhub

EXPOSE 8000 8899

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/proxyhub.conf"]
