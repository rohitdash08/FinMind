# FinMind — GCP Cloud Run Deployment

## Overview

Deploys FinMind to Google Cloud Run with:
- Cloud Run services for backend + frontend
- Cloud SQL for PostgreSQL
- Memorystore for Redis
- Artifact Registry for container images
- Cloud Build CI/CD pipeline
- Secret Manager for credentials

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
- A GCP project with billing enabled
- Docker installed (for local builds)

## Quick Deploy

```bash
chmod +x deploy/gcp/deploy.sh
./deploy/gcp/deploy.sh
```

## Manual Deploy

### 1. Enable APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com
```

### 2. Create Artifact Registry

```bash
gcloud artifacts repositories create finmind \
  --repository-format=docker \
  --location=us-central1
```

### 3. Create Secrets

```bash
echo -n "$(openssl rand -hex 32)" | gcloud secrets create finmind-jwt-secret --data-file=-
```

### 4. Build & Deploy via Cloud Build

```bash
gcloud builds submit --config deploy/gcp/cloudbuild.yaml .
```

### 5. Or Deploy Service YAML Directly

```bash
gcloud run services replace deploy/gcp/service.yaml --region us-central1
```

## Files

| File | Description |
|------|-------------|
| `deploy.sh` | Automated deploy script (Cloud SQL + Memorystore + Cloud Run) |
| `cloudbuild.yaml` | Cloud Build CI/CD pipeline |
| `service.yaml` | Cloud Run service definition (Knative) |

## Cost Estimate

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| Cloud Run (2 services) | ~$0–15 (scale to zero) |
| Cloud SQL db-f1-micro | ~$10 |
| Memorystore Basic 1GB | ~$35 |
| **Total** | **~$45–60/mo** |
