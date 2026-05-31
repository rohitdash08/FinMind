#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-finmind-project}"
REGION="${GCP_REGION:-us-central1}"
IMAGE="gcr.io/$PROJECT_ID/finmind-backend:latest"

echo "=== Deploying FinMind to Cloud Run ==="

gcloud config set project "$PROJECT_ID"
gcloud builds submit --tag "$IMAGE" -f deploy/gcp/Dockerfile.cloudrun

gcloud run deploy finmind-backend \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 5 \
  --concurrency 80 \
  --timeout 300 \
  --set-env-vars "LOG_LEVEL=INFO,GEMINI_MODEL=gemini-1.5-flash" \
  --update-secrets "DATABASE_URL=finmind-secrets:DATABASE_URL:latest" \
  --update-secrets "JWT_SECRET=finmind-secrets:JWT_SECRET:latest"

echo "Deploy complete. Service URL:"
gcloud run services describe finmind-backend --region "$REGION" --format='value(status.url)'
