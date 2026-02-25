#!/bin/bash
set -euo pipefail

# FinMind — GCP Cloud Run Deployment Script
# ──────────────────────────────────────────
# Prerequisites: gcloud CLI configured, Docker installed
# Usage: ./deploy/gcp/deploy.sh

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
DB_INSTANCE="finmind-db"
REDIS_INSTANCE="finmind-redis"
REPO="finmind"

if [ -z "$PROJECT_ID" ]; then
  echo "❌ No GCP project set. Run 'gcloud config set project PROJECT_ID' first."
  exit 1
fi

echo "╔══════════════════════════════════════════╗"
echo "║  FinMind — GCP Cloud Run Deployment      ║"
echo "╚══════════════════════════════════════════╝"
echo "  Project: $PROJECT_ID"
echo "  Region:  $REGION"
echo ""

# ── 1. Enable APIs ────────────────────────────────
echo "🔧 Enabling required APIs..."
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT_ID"

# ── 2. Create Artifact Registry ───────────────────
echo "📦 Creating Artifact Registry..."
gcloud artifacts repositories describe "$REPO" \
  --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || \
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT_ID"

# ── 3. Build and Push Images ──────────────────────
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

echo "🔨 Building and pushing backend..."
gcloud builds submit packages/backend/ \
  --tag "${REGISTRY}/finmind-backend:latest" \
  --project="$PROJECT_ID"

echo "🔨 Building and pushing frontend..."
gcloud builds submit app/ \
  --tag "${REGISTRY}/finmind-frontend:latest" \
  --project="$PROJECT_ID"

# ── 4. Create Cloud SQL Instance ──────────────────
echo "🐘 Creating Cloud SQL PostgreSQL instance..."
if ! gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT_ID" 2>/dev/null; then
  gcloud sql instances create "$DB_INSTANCE" \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --root-password="$DB_PASSWORD" \
    --storage-size=10GB \
    --storage-auto-increase \
    --project="$PROJECT_ID"

  gcloud sql databases create finmind \
    --instance="$DB_INSTANCE" \
    --project="$PROJECT_ID"

  gcloud sql users create finmind \
    --instance="$DB_INSTANCE" \
    --password="$DB_PASSWORD" \
    --project="$PROJECT_ID"
fi

DB_CONNECTION=$(gcloud sql instances describe "$DB_INSTANCE" \
  --format='value(connectionName)' --project="$PROJECT_ID")

# ── 5. Create Memorystore Redis ───────────────────
echo "🔴 Creating Memorystore Redis instance..."
if ! gcloud redis instances describe "$REDIS_INSTANCE" --region="$REGION" --project="$PROJECT_ID" 2>/dev/null; then
  gcloud redis instances create "$REDIS_INSTANCE" \
    --size=1 \
    --region="$REGION" \
    --redis-version=redis_7_0 \
    --project="$PROJECT_ID"
fi

REDIS_HOST=$(gcloud redis instances describe "$REDIS_INSTANCE" \
  --region="$REGION" --format='value(host)' --project="$PROJECT_ID")

# ── 6. Create Secrets ─────────────────────────────
echo "🔐 Creating secrets..."
echo -n "$JWT_SECRET" | gcloud secrets create finmind-jwt-secret --data-file=- --project="$PROJECT_ID" 2>/dev/null || \
echo -n "$JWT_SECRET" | gcloud secrets versions add finmind-jwt-secret --data-file=- --project="$PROJECT_ID"

DATABASE_URL="postgresql+psycopg2://finmind:${DB_PASSWORD}@/${DB_INSTANCE}?host=/cloudsql/${DB_CONNECTION}"
echo -n "$DATABASE_URL" | gcloud secrets create finmind-database-url --data-file=- --project="$PROJECT_ID" 2>/dev/null || \
echo -n "$DATABASE_URL" | gcloud secrets versions add finmind-database-url --data-file=- --project="$PROJECT_ID"

REDIS_URL="redis://${REDIS_HOST}:6379/0"
echo -n "$REDIS_URL" | gcloud secrets create finmind-redis-url --data-file=- --project="$PROJECT_ID" 2>/dev/null || \
echo -n "$REDIS_URL" | gcloud secrets versions add finmind-redis-url --data-file=- --project="$PROJECT_ID"

# ── 7. Deploy Backend to Cloud Run ────────────────
echo "🚀 Deploying backend to Cloud Run..."
gcloud run deploy finmind-backend \
  --image="${REGISTRY}/finmind-backend:latest" \
  --region="$REGION" \
  --platform=managed \
  --port=8000 \
  --allow-unauthenticated \
  --add-cloudsql-instances="$DB_CONNECTION" \
  --set-secrets="DATABASE_URL=finmind-database-url:latest,JWT_SECRET=finmind-jwt-secret:latest,REDIS_URL=finmind-redis-url:latest" \
  --set-env-vars="GEMINI_MODEL=gemini-1.5-flash,LOG_LEVEL=INFO" \
  --min-instances=0 \
  --max-instances=5 \
  --memory=512Mi \
  --cpu=1 \
  --project="$PROJECT_ID"

BACKEND_URL=$(gcloud run services describe finmind-backend \
  --region="$REGION" --format='value(status.url)' --project="$PROJECT_ID")

# ── 8. Deploy Frontend to Cloud Run ───────────────
echo "🚀 Deploying frontend to Cloud Run..."
gcloud run deploy finmind-frontend \
  --image="${REGISTRY}/finmind-frontend:latest" \
  --region="$REGION" \
  --platform=managed \
  --port=80 \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --memory=256Mi \
  --cpu=1 \
  --project="$PROJECT_ID"

FRONTEND_URL=$(gcloud run services describe finmind-frontend \
  --region="$REGION" --format='value(status.url)' --project="$PROJECT_ID")

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ FinMind deployed to GCP!             ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Frontend: $FRONTEND_URL"
echo "║  Backend:  $BACKEND_URL"
echo "║  Health:   $BACKEND_URL/health"
echo "╠══════════════════════════════════════════╣"
echo "║  DB Connection: $DB_CONNECTION"
echo "║  Redis Host:    $REDIS_HOST"
echo "╚══════════════════════════════════════════╝"
