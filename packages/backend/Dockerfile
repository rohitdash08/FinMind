# Production Dockerfile
# Multi-stage build for optimized production image

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Production - Runtime image
# ============================================================================
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# Security: Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appgroup app /app/app
COPY --chown=appuser:appgroup wsgi.py /app/wsgi.py
COPY --chown=appuser:appgroup .dockerignore /app/.dockerignore

# Create Prometheus metrics directory
RUN mkdir -p $PROMETHEUS_MULTIPROC_DIR && chown -R appuser:appgroup $PROMETHEUS_MULTIPROC_DIR

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health') or exit(1)" || exit 1

# Run with Gunicorn (4 workers, production settings)
CMD ["gunicorn", "--workers", "4", "--worker-class", "gthread", "--worker-connections", "1000", "--max-requests", "10000", "--max-requests-jitter", "500", "--timeout", "120", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", "wsgi:app"]