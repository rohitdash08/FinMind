# GCP Cloud Run Deployment Guide

## Prerequisites
- `gcloud` CLI installed and configured
- GCP project with billing enabled
- Cloud SQL PostgreSQL instance
- Memorystore Redis instance (or Upstash)

## Steps

1. **Create secrets in Secret Manager:**
   ```bash
   echo -n "postgresql+psycopg2://user:pass@/finmind?host=/cloudsql/PROJECT:REGION:INSTANCE" | \
     gcloud secrets create finmind-database-url --data-file=-

   echo -n "redis://redis-host:6379/0" | \
     gcloud secrets create finmind-redis-url --data-file=-

   echo -n "$(openssl rand -hex 32)" | \
     gcloud secrets create finmind-jwt-secret --data-file=-
   ```

2. **Deploy via Cloud Build:**
   ```bash
   gcloud builds submit --config deploy/gcp/cloudbuild.yaml
   ```
   This builds both images, pushes to GCR, and deploys to Cloud Run.

3. **Or deploy manually:**
   ```bash
   # Build and push
   gcloud builds submit --tag gcr.io/$PROJECT_ID/finmind-backend packages/backend
   gcloud builds submit --tag gcr.io/$PROJECT_ID/finmind-frontend app

   # Deploy backend
   gcloud run deploy finmind-backend \
     --image gcr.io/$PROJECT_ID/finmind-backend \
     --platform managed --region us-east1 --port 8000 \
     --allow-unauthenticated \
     --update-secrets=DATABASE_URL=finmind-database-url:latest,REDIS_URL=finmind-redis-url:latest,JWT_SECRET=finmind-jwt-secret:latest

   # Deploy frontend
   gcloud run deploy finmind-frontend \
     --image gcr.io/$PROJECT_ID/finmind-frontend \
     --platform managed --region us-east1 --port 80 \
     --allow-unauthenticated
   ```

## Endpoints
```bash
gcloud run services describe finmind-backend --region us-east1 --format 'value(status.url)'
gcloud run services describe finmind-frontend --region us-east1 --format 'value(status.url)'
```

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
