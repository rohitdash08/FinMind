# =============================================================================
# FinMind Backend - Multi-Stage Production Dockerfile
# =============================================================================
# Stage 1: Build dependencies in a full image
# Stage 2: Copy only what's needed into a slim runtime image
# Result: ~60% smaller image, faster deploys, reduced attack surface
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder - install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build-time system dependencies for compiling native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime - minimal production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Gunicorn tuning defaults (overridable at runtime)
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_BIND=0.0.0.0:8000 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

WORKDIR /app

# Runtime-only system dependency: libpq for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
  && rm -rf /var/lib/apt/lists/* \
  && addgroup --system --gid 1001 finmind \
  && adduser --system --uid 1001 --ingroup finmind finmind

# Copy pre-built Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY app /app/app
COPY wsgi.py /app/wsgi.py

# Prepare prometheus multiproc directory
RUN mkdir -p ${PROMETHEUS_MULTIPROC_DIR} && \
    chown -R finmind:finmind /app ${PROMETHEUS_MULTIPROC_DIR}

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

USER finmind
EXPOSE 8000

# Entrypoint: init DB then start gunicorn
CMD ["sh", "-c", \
  "python -m flask --app wsgi:app init-db && \
   rm -rf ${PROMETHEUS_MULTIPROC_DIR}/* && \
   gunicorn \
     --workers=${GUNICORN_WORKERS} \
     --threads=${GUNICORN_THREADS} \
     --bind=${GUNICORN_BIND} \
     --access-logfile=- \
     --error-logfile=- \
     --timeout=120 \
     --graceful-timeout=30 \
     wsgi:app"]
