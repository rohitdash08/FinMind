#!/bin/bash
# FinMind - Google Cloud Run Deployment
set -euo pipefail
PROJECT=${GCP_PROJECT:-finmind}
REGION=${GCP_REGION:-us-central1}
echo "☁️ Deploying FinMind to GCP Cloud Run..."
gcloud builds submit --tag gcr.io/$PROJECT/finmind-backend --project $PROJECT ../../ --dockerfile deploy/docker/Dockerfile.backend
gcloud run deploy finmind-backend --image gcr.io/$PROJECT/finmind-backend --region $REGION --allow-unauthenticated --port 8000
gcloud builds submit --tag gcr.io/$PROJECT/finmind-frontend --project $PROJECT ../../ --dockerfile deploy/docker/Dockerfile.frontend
gcloud run deploy finmind-frontend --image gcr.io/$PROJECT/finmind-frontend --region $REGION --allow-unauthenticated --port 80
echo "✅ Deployed to Cloud Run!"
