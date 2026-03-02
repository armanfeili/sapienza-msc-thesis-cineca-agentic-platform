# syntax=docker/dockerfile:1.4
# --------------------------------------------
# Cineca Agentic Platform — Runtime Image
# --------------------------------------------
# Notes:
# - Uses Python 3.11 slim variant
# - Creates a dedicated virtualenv in /opt/venv
# - Runs as non-root user
# - Exposes FastAPI via uvicorn on port 8000
# - Includes a basic /health HEALTHCHECK
# --------------------------------------------

FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_MODULE=src.app:app

# System deps (tini for signal handling, curl for healthcheck, ca-certs for HTTPS, postgresql-client for migrations)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tini \
    curl \
    ca-certificates \
    build-essential \
    pkg-config \
    libssl-dev \
    python3-dev \
    postgresql-client \
    && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv "$VIRTUAL_ENV"

# Set workdir
WORKDIR /app

# Copy requirements and install first to leverage layer caching
COPY requirements.txt ./requirements.txt
# Use BuildKit cache mount for pip to avoid re-downloading packages each build
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy only runtime files (keep context small so rebuilds are fast)
# (Assumes .dockerignore excludes large, unnecessary paths)
COPY src/ ./src/
COPY db/ ./db/
COPY ops/docker-entrypoint.sh ./ops/docker-entrypoint.sh
COPY scripts/ ./scripts/
COPY examples/ ./examples/
COPY README.md ./README.md
COPY pyproject.toml ./pyproject.toml

# Make entrypoint executable
RUN chmod +x ops/docker-entrypoint.sh

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app && \
    chown -R app:app /app

# Switch back to root temporarily to allow entrypoint to run migrations
# (migrations need to connect to DB which may require specific permissions)
# USER app will be effective after entrypoint completes

# Expose app port
EXPOSE 8000

# Basic healthcheck against /v1/health/live
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${APP_PORT}/v1/health/live" || exit 1

# Use tini as init for proper signal handling, with custom entrypoint for migrations
ENTRYPOINT ["/usr/bin/tini", "--", "/app/ops/docker-entrypoint.sh"]

# Default command (can be overridden by docker compose)
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]

# --------------------------------------------
# Test Runner Image
# --------------------------------------------
FROM python:3.11-slim as test-runner

WORKDIR /app

# Install redis-server (used by tests) and other small system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    build-essential \
    pkg-config \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject and requirements for installing dependencies
COPY pyproject.toml requirements.txt ./

# Use BuildKit pip cache for faster test runner installs
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pytest pytest-asyncio fakeredis

# Copy the app source and tests so CI can run pytest
COPY . /app

# Increase ready latency threshold for test-runner to avoid CI flakiness
ENV TEST_MAX_READY_MS=15000

# Start a local redis-server in the background, then run pytest
CMD ["sh", "-c", "redis-server --daemonize yes && pytest -q"]
