# Google Cloud Platform Deployment

## Cloud Run (Recommended)

### Prerequisites
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com containerregistry.googleapis.com secretmanager.googleapis.com
```

### 1. Build and Push Image
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/finmind-backend packages/backend/
```

### 2. Create Cloud SQL PostgreSQL
```bash
gcloud sql instances create finmind-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=us-central1

gcloud sql databases create finmind --instance=finmind-db
gcloud sql users create finmind --instance=finmind-db --password=YOUR_PASSWORD
```

### 3. Create Memorystore Redis
```bash
gcloud redis instances create finmind-redis \
  --size=1 \
  --region=us-central1 \
  --redis-version=redis_7_0
```

### 4. Store Secrets
```bash
echo -n "postgresql://..." | gcloud secrets create database-url --data-file=-
echo -n "redis://..." | gcloud secrets create redis-url --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create jwt-secret --data-file=-
```

### 5. Deploy
```bash
# Update PROJECT_ID in cloudrun.yaml
gcloud run services replace deploy/gcp/cloudrun.yaml --region us-central1

# Or direct deploy
gcloud run deploy finmind-backend \
  --image gcr.io/PROJECT_ID/finmind-backend:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets="DATABASE_URL=database-url:latest,REDIS_URL=redis-url:latest,JWT_SECRET=jwt-secret:latest"
```

## Frontend (Firebase Hosting)

```bash
cd app
npm run build
firebase init hosting
firebase deploy
```

## Cost Estimate

- Cloud Run: ~$0-10/month (pay per request)
- Cloud SQL f1-micro: ~$8/month
- Memorystore 1GB: ~$35/month (or use free-tier Redis Cloud)
- Firebase Hosting: Free tier
