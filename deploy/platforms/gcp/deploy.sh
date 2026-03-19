#!/usr/bin/env bash
# FinMind — One-click GCP Cloud Run deployment
# Prerequisites: gcloud CLI authenticated, PROJECT_ID set
# Usage: PROJECT_ID=my-project REGION=us-central1 ./deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKEND_IMAGE="ghcr.io/rohitdash08/finmind-backend:${IMAGE_TAG}"
FRONTEND_IMAGE="ghcr.io/rohitdash08/finmind-frontend:${IMAGE_TAG}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

# Deploy backend
log "Deploying backend to Cloud Run..."
gcloud run deploy finmind-backend \
  --image "$BACKEND_IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8000 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 10 \
  --concurrency 80 \
  --set-env-vars "LOG_LEVEL=INFO,GEMINI_MODEL=gemini-1.5-flash,PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc" \
  --set-secrets "POSTGRES_USER=finmind-postgres-user:latest,POSTGRES_PASSWORD=finmind-postgres-password:latest,POSTGRES_DB=finmind-postgres-db:latest,DATABASE_URL=finmind-database-url:latest,REDIS_URL=finmind-redis-url:latest,JWT_SECRET=finmind-jwt-secret:latest,GEMINI_API_KEY=finmind-gemini-api-key:latest" \
  --command "sh,-c" \
  --args "python -m flask --app wsgi:app init-db && rm -rf \$PROMETHEUS_MULTIPROC_DIR && mkdir -p \$PROMETHEUS_MULTIPROC_DIR && exec gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app"

BACKEND_URL=$(gcloud run services describe finmind-backend --region "$REGION" --format 'value(status.url)')
log "Backend deployed: $BACKEND_URL"

# Deploy frontend
log "Deploying frontend to Cloud Run..."
gcloud run deploy finmind-frontend \
  --image "$FRONTEND_IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 80 \
  --memory 256Mi \
  --cpu 0.5 \
  --min-instances 1 \
  --max-instances 5 \
  --set-env-vars "VITE_API_URL=${BACKEND_URL}"

FRONTEND_URL=$(gcloud run services describe finmind-frontend --region "$REGION" --format 'value(status.url)')
log "Frontend deployed: $FRONTEND_URL"
log "Open: $FRONTEND_URL"
