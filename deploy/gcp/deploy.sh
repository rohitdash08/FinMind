#!/usr/bin/env bash
# ============================================================================
# FinMind — GCP Cloud Run Deployment Script
# ============================================================================
# Deploys backend (Python/Flask) + frontend (React/nginx) to Cloud Run
# with Cloud SQL (PostgreSQL) and Memorystore (Redis).
#
# Prerequisites:
#   - gcloud CLI authenticated with appropriate permissions
#   - Docker installed and running
#   - APIs enabled: run, sqladmin, redis, vpcaccess, secretmanager, cloudbuild
#
# Usage:
#   ./deploy.sh [--project PROJECT_ID] [--region us-central1]
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
PROJECT_NAME="finmind"
BACKEND_SERVICE="${PROJECT_NAME}-backend"
FRONTEND_SERVICE="${PROJECT_NAME}-frontend"
SQL_INSTANCE="${PROJECT_NAME}-postgres"
REDIS_INSTANCE="${PROJECT_NAME}-redis"
VPC_CONNECTOR="${PROJECT_NAME}-vpc-connector"
NETWORK="default"
BACKEND_DOCKERFILE="packages/backend/Dockerfile"
FRONTEND_DOCKERFILE="app/Dockerfile"

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region)  REGION="$2"; shift 2 ;;
    *)         echo "Unknown option: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== FinMind GCP Cloud Run Deployment ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo ""

gcloud config set project "${PROJECT_ID}"

# ---------------------------------------------------------------------------
# Step 1: Enable required APIs
# ---------------------------------------------------------------------------
echo ">>> Step 1: Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  --quiet

# ---------------------------------------------------------------------------
# Step 2: Create Cloud SQL PostgreSQL instance
# ---------------------------------------------------------------------------
echo ">>> Step 2: Creating Cloud SQL PostgreSQL instance..."
if ! gcloud sql instances describe "${SQL_INSTANCE}" --quiet 2>/dev/null; then
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="${REGION}" \
    --storage-size=10GB \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --availability-type=zonal \
    --labels=app=finmind \
    --quiet

  # Create database and user
  gcloud sql databases create finmind --instance="${SQL_INSTANCE}" --quiet
  DB_PASSWORD=$(openssl rand -base64 32)
  gcloud sql users create finmind \
    --instance="${SQL_INSTANCE}" \
    --password="${DB_PASSWORD}" \
    --quiet

  CLOUD_SQL_CONN="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
  DATABASE_URL="postgresql://finmind:${DB_PASSWORD}@/finmind?host=/cloudsql/${CLOUD_SQL_CONN}"

  echo "  Cloud SQL instance created: ${SQL_INSTANCE}"
  echo "  Connection: ${CLOUD_SQL_CONN}"
else
  CLOUD_SQL_CONN="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
  echo "  Cloud SQL instance already exists: ${SQL_INSTANCE}"
  echo "  Ensure DATABASE_URL secret is set in Secret Manager."
  DATABASE_URL=""
fi

# ---------------------------------------------------------------------------
# Step 3: Create Memorystore Redis instance
# ---------------------------------------------------------------------------
echo ">>> Step 3: Creating Memorystore Redis instance..."
if ! gcloud redis instances describe "${REDIS_INSTANCE}" --region="${REGION}" --quiet 2>/dev/null; then
  gcloud redis instances create "${REDIS_INSTANCE}" \
    --size=1 \
    --region="${REGION}" \
    --redis-version=redis_7_0 \
    --network="${NETWORK}" \
    --labels=app=finmind \
    --quiet

  REDIS_HOST=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
    --region="${REGION}" --format='value(host)')
  REDIS_PORT=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
    --region="${REGION}" --format='value(port)')
  REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"

  echo "  Redis instance created: ${REDIS_INSTANCE} (${REDIS_HOST}:${REDIS_PORT})"
else
  REDIS_HOST=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
    --region="${REGION}" --format='value(host)' 2>/dev/null || echo "")
  REDIS_PORT=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
    --region="${REGION}" --format='value(port)' 2>/dev/null || echo "6379")
  REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"
  echo "  Redis instance already exists: ${REDIS_INSTANCE}"
fi

# ---------------------------------------------------------------------------
# Step 4: Create VPC connector (for Cloud SQL + Redis access)
# ---------------------------------------------------------------------------
echo ">>> Step 4: Creating Serverless VPC Access connector..."
if ! gcloud compute networks vpc-access connectors describe "${VPC_CONNECTOR}" \
    --region="${REGION}" --quiet 2>/dev/null; then
  gcloud compute networks vpc-access connectors create "${VPC_CONNECTOR}" \
    --region="${REGION}" \
    --network="${NETWORK}" \
    --range="10.8.0.0/28" \
    --min-instances=2 \
    --max-instances=10 \
    --quiet
  echo "  VPC connector created: ${VPC_CONNECTOR}"
else
  echo "  VPC connector already exists: ${VPC_CONNECTOR}"
fi

# ---------------------------------------------------------------------------
# Step 5: Store secrets in Secret Manager
# ---------------------------------------------------------------------------
echo ">>> Step 5: Storing secrets in Secret Manager..."

store_secret() {
  local name=$1
  local value=$2
  if ! gcloud secrets describe "${name}" --quiet 2>/dev/null; then
    echo -n "${value}" | gcloud secrets create "${name}" \
      --data-file=- \
      --replication-policy=automatic \
      --labels=app=finmind \
      --quiet
    echo "  Created secret: ${name}"
  else
    echo "  Secret already exists: ${name} (update manually if needed)"
  fi
}

if [[ -n "${DATABASE_URL}" ]]; then
  store_secret "finmind-database-url" "${DATABASE_URL}"
fi
if [[ -n "${REDIS_URL}" ]]; then
  store_secret "finmind-redis-url" "${REDIS_URL}"
fi
store_secret "finmind-jwt-secret" "$(openssl rand -base64 64)"
store_secret "finmind-gemini-api-key" "${GEMINI_API_KEY:-REPLACE_ME}"

# Grant Cloud Run service account access to secrets
SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"
for secret in finmind-database-url finmind-redis-url finmind-jwt-secret finmind-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null || true
done

# ---------------------------------------------------------------------------
# Step 6: Build and push Docker images
# ---------------------------------------------------------------------------
echo ">>> Step 6: Building and pushing Docker images..."

IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"

# Backend
echo "  Building backend..."
docker build \
  -t "gcr.io/${PROJECT_ID}/${BACKEND_SERVICE}:${IMAGE_TAG}" \
  -t "gcr.io/${PROJECT_ID}/${BACKEND_SERVICE}:latest" \
  -f "${PROJECT_ROOT}/${BACKEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/packages/backend"

docker push "gcr.io/${PROJECT_ID}/${BACKEND_SERVICE}:${IMAGE_TAG}"
docker push "gcr.io/${PROJECT_ID}/${BACKEND_SERVICE}:latest"

# Frontend
echo "  Building frontend..."
docker build \
  -t "gcr.io/${PROJECT_ID}/${FRONTEND_SERVICE}:${IMAGE_TAG}" \
  -t "gcr.io/${PROJECT_ID}/${FRONTEND_SERVICE}:latest" \
  -f "${PROJECT_ROOT}/${FRONTEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/app"

docker push "gcr.io/${PROJECT_ID}/${FRONTEND_SERVICE}:${IMAGE_TAG}"
docker push "gcr.io/${PROJECT_ID}/${FRONTEND_SERVICE}:latest"

# ---------------------------------------------------------------------------
# Step 7: Deploy backend to Cloud Run
# ---------------------------------------------------------------------------
echo ">>> Step 7: Deploying backend to Cloud Run..."
gcloud run deploy "${BACKEND_SERVICE}" \
  --image="gcr.io/${PROJECT_ID}/${BACKEND_SERVICE}:${IMAGE_TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --port=8000 \
  --cpu=1 \
  --memory=512Mi \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=80 \
  --timeout=300s \
  --set-env-vars="LOG_LEVEL=info,GEMINI_MODEL=gemini-pro" \
  --set-secrets="DATABASE_URL=finmind-database-url:latest,REDIS_URL=finmind-redis-url:latest,JWT_SECRET=finmind-jwt-secret:latest,GEMINI_API_KEY=finmind-gemini-api-key:latest" \
  --add-cloudsql-instances="${CLOUD_SQL_CONN}" \
  --vpc-connector="${VPC_CONNECTOR}" \
  --ingress=all \
  --allow-unauthenticated \
  --labels=app=finmind,component=backend \
  --quiet

BACKEND_URL=$(gcloud run services describe "${BACKEND_SERVICE}" \
  --region="${REGION}" --format='value(status.url)')
echo "  Backend deployed: ${BACKEND_URL}"

# ---------------------------------------------------------------------------
# Step 8: Deploy frontend to Cloud Run
# ---------------------------------------------------------------------------
echo ">>> Step 8: Deploying frontend to Cloud Run..."
gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="gcr.io/${PROJECT_ID}/${FRONTEND_SERVICE}:${IMAGE_TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --port=80 \
  --cpu=1 \
  --memory=256Mi \
  --min-instances=0 \
  --max-instances=5 \
  --concurrency=200 \
  --timeout=60s \
  --set-env-vars="VITE_API_URL=${BACKEND_URL}" \
  --ingress=all \
  --allow-unauthenticated \
  --labels=app=finmind,component=frontend \
  --quiet

FRONTEND_URL=$(gcloud run services describe "${FRONTEND_SERVICE}" \
  --region="${REGION}" --format='value(status.url)')
echo "  Frontend deployed: ${FRONTEND_URL}"

# ---------------------------------------------------------------------------
# Step 9: Verify health
# ---------------------------------------------------------------------------
echo ">>> Step 9: Verifying deployment health..."
echo "  Checking backend health endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/health" || echo "000")
if [[ "${HTTP_STATUS}" == "200" ]]; then
  echo "  Backend health check: PASSED (HTTP ${HTTP_STATUS})"
else
  echo "  Backend health check: FAILED (HTTP ${HTTP_STATUS})"
  echo "  Check logs: gcloud run logs read ${BACKEND_SERVICE} --region=${REGION} --limit=50"
fi

echo ""
echo "=== Deployment Complete ==="
echo "Backend:  ${BACKEND_URL}"
echo "Frontend: ${FRONTEND_URL}"
echo ""
echo "Useful commands:"
echo "  gcloud run logs read ${BACKEND_SERVICE} --region=${REGION} --limit=50"
echo "  gcloud run services describe ${BACKEND_SERVICE} --region=${REGION}"
echo "  gcloud run services describe ${FRONTEND_SERVICE} --region=${REGION}"
