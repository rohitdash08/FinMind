# Deploy FinMind on GCP Cloud Run

## Quick Deploy

```bash
export GCP_PROJECT_ID=your-project-id
chmod +x deploy/gcp/deploy.sh
./deploy/gcp/deploy.sh
```

## What Gets Created

- Artifact Registry (Docker images)
- Cloud SQL PostgreSQL 16
- Memorystore Redis
- VPC Connector
- Cloud Run services (API + Frontend)

## Cleanup

```bash
gcloud run services delete finmind-api finmind-web --region us-central1
gcloud sql instances delete finmind-db
gcloud redis instances delete finmind-redis --region us-central1
```

## Cost

~$15-30/month (Cloud Run scales to zero, pay for Cloud SQL + Redis minimum)
