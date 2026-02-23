#!/bin/bash
set -euo pipefail

# FinMind - GCP Cloud Run Deployment Script

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"

echo "🚀 Deploying FinMind to GCP Cloud Run..."
echo "   Project: $PROJECT_ID | Region: $REGION"

# Enable APIs
echo "📡 Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  artifactregistry.googleapis.com \
  --project "$PROJECT_ID"

# Create Artifact Registry repo
echo "📦 Creating Artifact Registry..."
gcloud artifacts repositories create finmind \
  --repository-format=docker \
  --location="$REGION" \
  --project "$PROJECT_ID" 2>/dev/null || true

# Build and push images
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/finmind"

echo "🔨 Building backend..."
gcloud builds submit \
  --tag "${REGISTRY}/api:latest" \
  --project "$PROJECT_ID" \
  --gcs-log-dir="gs://${PROJECT_ID}_cloudbuild/logs" \
  -f packages/backend/Dockerfile .

echo "🔨 Building frontend..."
gcloud builds submit \
  --tag "${REGISTRY}/web:latest" \
  --project "$PROJECT_ID" \
  -f app/Dockerfile app/

# Create Cloud SQL instance
echo "🐘 Creating Cloud SQL PostgreSQL..."
gcloud sql instances create finmind-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region="$REGION" \
  --project "$PROJECT_ID" 2>/dev/null || true

gcloud sql databases create finmind \
  --instance=finmind-db \
  --project "$PROJECT_ID" 2>/dev/null || true

gcloud sql users set-password postgres \
  --instance=finmind-db \
  --password="$DB_PASSWORD" \
  --project "$PROJECT_ID"

SQL_CONNECTION=$(gcloud sql instances describe finmind-db --format='value(connectionName)' --project "$PROJECT_ID")

# Create Memorystore Redis
echo "🔴 Creating Memorystore Redis..."
gcloud redis instances create finmind-redis \
  --size=1 \
  --region="$REGION" \
  --project "$PROJECT_ID" 2>/dev/null || true

REDIS_HOST=$(gcloud redis instances describe finmind-redis --region="$REGION" --format='value(host)' --project "$PROJECT_ID")

# Create VPC connector for Cloud Run → Redis/SQL
echo "🔗 Creating VPC connector..."
gcloud compute networks vpc-access connectors create finmind-connector \
  --region="$REGION" \
  --range="10.8.0.0/28" \
  --project "$PROJECT_ID" 2>/dev/null || true

# Deploy backend to Cloud Run
echo "🚀 Deploying backend..."
gcloud run deploy finmind-api \
  --image "${REGISTRY}/api:latest" \
  --platform managed \
  --region "$REGION" \
  --port 8000 \
  --allow-unauthenticated \
  --set-env-vars "LOG_LEVEL=INFO" \
  --set-env-vars "DATABASE_URL=postgresql+psycopg2://postgres:${DB_PASSWORD}@/${SQL_CONNECTION}/finmind" \
  --set-env-vars "REDIS_URL=redis://${REDIS_HOST}:6379/0" \
  --set-env-vars "JWT_SECRET=${JWT_SECRET}" \
  --add-cloudsql-instances "$SQL_CONNECTION" \
  --vpc-connector finmind-connector \
  --min-instances 0 \
  --max-instances 3 \
  --project "$PROJECT_ID"

BACKEND_URL=$(gcloud run services describe finmind-api --region="$REGION" --format='value(status.url)' --project "$PROJECT_ID")

# Deploy frontend
echo "🚀 Deploying frontend..."
gcloud run deploy finmind-web \
  --image "${REGISTRY}/web:latest" \
  --platform managed \
  --region "$REGION" \
  --port 80 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --project "$PROJECT_ID"

FRONTEND_URL=$(gcloud run services describe finmind-web --region="$REGION" --format='value(status.url)' --project "$PROJECT_ID")

echo ""
echo "🎉 FinMind deployed successfully!"
echo "   Frontend: $FRONTEND_URL"
echo "   Backend:  $BACKEND_URL"
echo "   Health:   $BACKEND_URL/health"
