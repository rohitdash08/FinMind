# Deploy FinMind to Google Cloud Run

## Prerequisites
- Google Cloud SDK installed
- Cloud SQL PostgreSQL instance
- Memorystore Redis instance
- Secrets stored in Secret Manager

## Deploy
```bash
# Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# Build and deploy via Cloud Build
gcloud builds submit --config deploy/platforms/gcp-cloudrun/cloudbuild.yaml

# Or deploy directly
gcloud run deploy finmind-backend \
    --source packages/backend \
    --region us-central1 \
    --port 8000 \
    --set-env-vars LOG_LEVEL=INFO \
    --set-secrets DATABASE_URL=finmind-db-url:latest,JWT_SECRET=finmind-jwt:latest \
    --allow-unauthenticated

gcloud run deploy finmind-frontend \
    --source app \
    --region us-central1 \
    --port 80 \
    --allow-unauthenticated
```
