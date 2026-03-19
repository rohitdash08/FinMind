#!/usr/bin/env bash
# FinMind - Google Cloud Run Deployment
# Prerequisites: gcloud CLI configured, project selected
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"

echo "=== FinMind GCP Cloud Run Deployment ==="

# Step 1: Enable required APIs
echo "Enabling APIs..."
gcloud services enable run.googleapis.com containerregistry.googleapis.com sqladmin.googleapis.com redis.googleapis.com --project="$PROJECT_ID"

# Step 2: Build and push images
echo "Building backend image..."
gcloud builds submit --tag "gcr.io/$PROJECT_ID/finmind-backend" ./packages/backend --project="$PROJECT_ID"

echo "Building frontend image..."
gcloud builds submit --tag "gcr.io/$PROJECT_ID/finmind-frontend" ./app --project="$PROJECT_ID"

# Step 3: Create secrets (if not exists)
for secret in DATABASE_URL REDIS_URL JWT_SECRET GEMINI_API_KEY; do
    if ! gcloud secrets describe "finmind-$secret" --project="$PROJECT_ID" &>/dev/null; then
        echo "Creating secret: finmind-$secret (set value manually)"
        echo -n "placeholder" | gcloud secrets create "finmind-$secret" --data-file=- --project="$PROJECT_ID"
    fi
done

# Step 4: Deploy backend
echo "Deploying backend to Cloud Run..."
gcloud run deploy finmind-backend \
    --image "gcr.io/$PROJECT_ID/finmind-backend:latest" \
    --region "$REGION" \
    --platform managed \
    --port 8000 \
    --min-instances 1 \
    --max-instances 10 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "GEMINI_MODEL=gemini-1.5-flash,LOG_LEVEL=INFO" \
    --set-secrets "DATABASE_URL=finmind-DATABASE_URL:latest,REDIS_URL=finmind-REDIS_URL:latest,JWT_SECRET=finmind-JWT_SECRET:latest,GEMINI_API_KEY=finmind-GEMINI_API_KEY:latest" \
    --allow-unauthenticated \
    --project="$PROJECT_ID"

# Step 5: Deploy frontend
echo "Deploying frontend to Cloud Run..."
BACKEND_URL=$(gcloud run services describe finmind-backend --region "$REGION" --format="value(status.url)" --project="$PROJECT_ID")
gcloud run deploy finmind-frontend \
    --image "gcr.io/$PROJECT_ID/finmind-frontend:latest" \
    --region "$REGION" \
    --platform managed \
    --port 80 \
    --min-instances 1 \
    --max-instances 5 \
    --memory 256Mi \
    --cpu 1 \
    --set-env-vars "VITE_API_URL=$BACKEND_URL" \
    --allow-unauthenticated \
    --project="$PROJECT_ID"

FRONTEND_URL=$(gcloud run services describe finmind-frontend --region "$REGION" --format="value(status.url)" --project="$PROJECT_ID")

echo ""
echo "=== Deployment complete! ==="
echo "Backend:  $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
