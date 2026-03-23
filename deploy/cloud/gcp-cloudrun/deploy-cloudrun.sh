#!/usr/bin/env bash
# deploy-cloudrun.sh — Deploy FinMind to Google Cloud Run
# Usage: ./deploy-cloudrun.sh [PROJECT_ID] [REGION]
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
BACKEND_IMAGE="gcr.io/${PROJECT_ID}/finmind-backend"
FRONTEND_IMAGE="gcr.io/${PROJECT_ID}/finmind-frontend"

echo "🚀 Deploying FinMind to Cloud Run in project: ${PROJECT_ID}, region: ${REGION}"

# ── Enable required APIs ─────────────────────────────────────────────────────
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  --project="${PROJECT_ID}" --quiet

# ── Build and push images ────────────────────────────────────────────────────
echo "📦 Building backend image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${BACKEND_IMAGE}" \
  --timeout=600s \
  packages/backend/

echo "📦 Building frontend image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${FRONTEND_IMAGE}" \
  --timeout=600s \
  app/

# ── Create secrets (if they don't exist) ─────────────────────────────────────
create_secret_if_missing() {
  local name="$1"
  if ! gcloud secrets describe "${name}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "🔐 Creating secret: ${name}"
    echo -n "${2:-changeme}" | gcloud secrets create "${name}" \
      --project="${PROJECT_ID}" \
      --replication-policy="automatic" \
      --data-file=-
    echo "   ⚠️  Update ${name} with real value: gcloud secrets versions add ${name} --data-file=-"
  fi
}

create_secret_if_missing "finmind-jwt-secret" "$(openssl rand -hex 32 2>/dev/null || echo changeme)"
create_secret_if_missing "finmind-database-url" "postgresql+psycopg2://finmind:changeme@/finmind?host=/cloudsql/PROJECT:REGION:INSTANCE"
create_secret_if_missing "finmind-redis-url" "redis://10.0.0.1:6379/0"

# ── Deploy backend ───────────────────────────────────────────────────────────
echo "🔧 Deploying backend..."
gcloud run deploy finmind-backend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${BACKEND_IMAGE}" \
  --platform=managed \
  --port=8000 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=60s \
  --concurrency=80 \
  --set-env-vars="LOG_LEVEL=INFO,GEMINI_MODEL=gemini-1.5-flash,PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc" \
  --set-secrets="DATABASE_URL=finmind-database-url:latest,REDIS_URL=finmind-redis-url:latest,JWT_SECRET=finmind-jwt-secret:latest" \
  --command="sh" \
  --args="-c,python -m flask --app wsgi:app init-db && rm -rf /tmp/prometheus_multiproc && mkdir -p /tmp/prometheus_multiproc && gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app" \
  --allow-unauthenticated \
  --quiet

BACKEND_URL=$(gcloud run services describe finmind-backend \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --format="value(status.url)")

echo "✅ Backend deployed: ${BACKEND_URL}"

# ── Deploy frontend ──────────────────────────────────────────────────────────
echo "🔧 Deploying frontend..."
gcloud run deploy finmind-frontend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${FRONTEND_IMAGE}" \
  --platform=managed \
  --port=80 \
  --memory=128Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --allow-unauthenticated \
  --quiet

FRONTEND_URL=$(gcloud run services describe finmind-frontend \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --format="value(status.url)")

echo "✅ Frontend deployed: ${FRONTEND_URL}"
echo ""
echo "📋 Summary:"
echo "   Backend:  ${BACKEND_URL}"
echo "   Frontend: ${FRONTEND_URL}"
echo ""
echo "⚠️  Next steps:"
echo "   1. Set up Cloud SQL PostgreSQL and Memorystore Redis"
echo "   2. Update secrets with real connection strings"
echo "   3. Rebuild frontend with VITE_API_URL=${BACKEND_URL}"
