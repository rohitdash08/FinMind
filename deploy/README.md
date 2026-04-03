# FinMind Deployment Guide

One-command deployment for each supported platform.

## Prerequisites
- Docker installed
- Git repo cloned
- Platform CLI installed (where applicable)

## Required Environment Variables
| Variable | Description | Example |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection string | postgresql://user:pass@host:5432/finmind |
| REDIS_URL | Redis connection string | redis://host:6379/0 |
| JWT_SECRET_KEY | Secret for JWT tokens | Generate: `openssl rand -hex 32` |

## Platform Deploy Commands

### Railway
```bash
railway init
railway up
railway variables set JWT_SECRET_KEY=$(openssl rand -hex 32)
```

### Heroku
```bash
heroku create finmind-app
heroku addons:create heroku-postgresql:mini
heroku addons:create heroku-redis:mini
heroku config:set JWT_SECRET_KEY=$(openssl rand -hex 32)
git push heroku main
```

### Render
Import `deploy/render.yaml` as a Render Blueprint.

### Fly.io
```bash
fly launch --config deploy/fly.toml
fly secrets set JWT_SECRET_KEY=$(openssl rand -hex 32)
fly deploy
```

### DigitalOcean App Platform
Import `deploy/digitalocean.yaml` in DO Console.

### AWS ECS Fargate
```bash
aws ecr create-repository --repository-name finmind
docker build -t finmind packages/backend/
docker tag finmind:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/finmind:latest
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/finmind:latest
aws ecs register-task-definition --cli-input-json file://deploy/aws-task-definition.json
```

### Google Cloud Run
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/finmind packages/backend/
gcloud run apply deploy/gcp-cloudrun.yaml
```

### Azure Container Apps
```bash
az containerapp create --environment finmind-env --resource-group myRG -f deploy/azure-containerapp.yaml
```

### Kubernetes (Helm)
```bash
kubectl apply -f deploy/kubernetes/namespace.yaml
helm install finmind deploy/helm/finmind \
  --namespace finmind \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgres.password=$(openssl rand -hex 16)
```

### Tilt (Local K8s Dev)
```bash
tilt up
```

## Post-Deploy Verification
1. Health check: `curl https://your-domain/health`
2. Auth: Register + Login via /auth/register, /auth/login
3. Core modules: Create expense, bill, check dashboard

## Docker Compose (Production)
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
