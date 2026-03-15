# =============================================================================
# FinMind Backend — Production Multi-Stage Dockerfile
# =============================================================================
# Stage 1: Build dependencies in a full image (compile psycopg2, etc.)
# Stage 2: Copy into slim runtime image for minimal attack surface
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build-time system dependencies required by psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtual-env so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY packages/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Labels for container registries
LABEL org.opencontainers.image.title="finmind-backend" \
      org.opencontainers.image.description="FinMind backend API server" \
      org.opencontainers.image.source="https://github.com/rohitdash08/FinMind"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Gunicorn tuning defaults (overridable at runtime)
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_BIND="0.0.0.0:8000" \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_GRACEFUL_TIMEOUT=30 \
    # Prometheus multi-process directory
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# Runtime-only system dependency: libpq for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini && \
    rm -rf /var/lib/apt/lists/* && \
    # Create non-root user
    groupadd -r finmind && \
    useradd -r -g finmind -d /app -s /sbin/nologin finmind

# Copy virtual-env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY packages/backend/app ./app
COPY packages/backend/wsgi.py ./wsgi.py

# Prepare prometheus multiproc directory
RUN mkdir -p ${PROMETHEUS_MULTIPROC_DIR} && \
    chown -R finmind:finmind /app ${PROMETHEUS_MULTIPROC_DIR}

# Switch to non-root user
USER finmind

EXPOSE 8000

# Health check — uses the /health endpoint built into the Flask app
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Use tini as PID 1 for proper signal handling
ENTRYPOINT ["tini", "--"]

# Initialize the database schema, then start gunicorn
CMD ["sh", "-c", "\
    python -m flask --app wsgi:app init-db && \
    rm -rf ${PROMETHEUS_MULTIPROC_DIR}/* && \
    exec gunicorn \
        --workers=${GUNICORN_WORKERS} \
        --threads=${GUNICORN_THREADS} \
        --bind=${GUNICORN_BIND} \
        --timeout=${GUNICORN_TIMEOUT} \
        --graceful-timeout=${GUNICORN_GRACEFUL_TIMEOUT} \
        --access-logfile=- \
        --error-logfile=- \
        --log-level=info \
        --forwarded-allow-ips='*' \
        wsgi:app"]
