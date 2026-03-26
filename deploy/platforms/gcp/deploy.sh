#!/usr/bin/env bash
# GCP Cloud Run Deployment Script
# Prerequisites: gcloud CLI authenticated, project configured
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="finmind-backend"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "======================================"
echo "  FinMind — GCP Cloud Run Deploy"
echo "======================================"

# 1. Enable required APIs
echo "[1/6] Enabling GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    redis.googleapis.com \
    --project "$PROJECT_ID" --quiet

# 2. Build with Cloud Build
echo "[2/6] Building with Cloud Build..."
gcloud builds submit \
    --tag "$IMAGE:latest" \
    --project "$PROJECT_ID" \
    packages/backend/

# 3. Create secrets (first-time only)
echo "[3/6] Setting up secrets..."
for secret in finmind-database-url finmind-redis-url finmind-jwt-secret finmind-gemini-key; do
    if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" &>/dev/null; then
        echo "  Creating secret: $secret (set value manually)"
        echo -n "placeholder" | gcloud secrets create "$secret" \
            --data-file=- --project "$PROJECT_ID" --quiet
    fi
done

# 4. Create Cloud SQL instance (first-time only)
echo "[4/6] Checking Cloud SQL..."
if ! gcloud sql instances describe finmind-db --project "$PROJECT_ID" &>/dev/null; then
    echo "  Creating Cloud SQL PostgreSQL 16 instance..."
    gcloud sql instances create finmind-db \
        --database-version=POSTGRES_16 \
        --tier=db-f1-micro \
        --region="$REGION" \
        --project "$PROJECT_ID" \
        --quiet
    gcloud sql databases create finmind --instance=finmind-db --project "$PROJECT_ID" --quiet
    gcloud sql users create finmind --instance=finmind-db --password="$(openssl rand -hex 16)" --project "$PROJECT_ID" --quiet
fi

# 5. Create Memorystore Redis (first-time only)
echo "[5/6] Checking Memorystore Redis..."
if ! gcloud redis instances describe finmind-redis --region="$REGION" --project "$PROJECT_ID" &>/dev/null; then
    echo "  Creating Memorystore Redis instance..."
    gcloud redis instances create finmind-redis \
        --size=1 \
        --region="$REGION" \
        --redis-version=redis_7_0 \
        --project "$PROJECT_ID" \
        --quiet
fi

# 6. Deploy to Cloud Run
echo "[6/6] Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE:latest" \
    --platform managed \
    --region "$REGION" \
    --port 8000 \
    --min-instances 1 \
    --max-instances 10 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "LOG_LEVEL=INFO,GEMINI_MODEL=gemini-1.5-flash" \
    --set-secrets "DATABASE_URL=finmind-database-url:latest,REDIS_URL=finmind-redis-url:latest,JWT_SECRET=finmind-jwt-secret:latest,GEMINI_API_KEY=finmind-gemini-key:latest" \
    --allow-unauthenticated \
    --project "$PROJECT_ID" \
    --quiet

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')
echo ""
echo "Deployed: $SERVICE_URL"
echo "Health:   $SERVICE_URL/health"
