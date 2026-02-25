# FinMind — Deployment Guide

FinMind supports multiple deployment methods, from local development to production-grade cloud platforms. Choose the one that fits your needs.

## Table of Contents

- [Local Development (Docker Compose)](#local-development-docker-compose)
- [Local K8s (Tilt)](#local-k8s-tilt)
- [Railway](#railway)
- [Heroku](#heroku)
- [Render](#render)
- [Fly.io](#flyio)
- [DigitalOcean App Platform](#digitalocean-app-platform)
- [DigitalOcean Droplet](#digitalocean-droplet)
- [AWS ECS Fargate](#aws-ecs-fargate)
- [AWS App Runner](#aws-app-runner)
- [AWS CloudFormation](#aws-cloudformation)
- [GCP Cloud Run](#gcp-cloud-run)
- [Azure Container Apps](#azure-container-apps)
- [Netlify (Frontend)](#netlify-frontend)
- [Vercel (Frontend)](#vercel-frontend)

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐
│   Frontend   │────▶│   Backend    │
│  (React/Vite)│     │  (Flask)     │
│   Port 80    │     │  Port 8000   │
└─────────────┘     └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │              │
              ┌─────▼─────┐ ┌─────▼─────┐
              │ PostgreSQL │ │   Redis    │
              │    16      │ │     7      │
              └───────────┘ └───────────┘
```

---

## Local Development (Docker Compose)

```bash
cp .env.example .env
# Edit .env and fill in API keys
docker compose up -d
```

| Service | URL |
|---------|-----|
| Backend | http://localhost:8000 |
| Frontend | http://localhost:5173 |
| Nginx | http://localhost:8080 |
| Grafana | http://localhost:3000 |

---

## Local K8s (Tilt)

Prerequisites: Install [Tilt](https://docs.tilt.dev/install.html) + a local K8s cluster (minikube/kind/Docker Desktop)

```bash
# 1. Create namespace and secrets
kubectl apply -f deploy/k8s/namespace.yaml
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml with real values
kubectl apply -f deploy/k8s/secrets.yaml

# 2. Start Tilt
tilt up
```

Tilt Dashboard: http://localhost:10350

---

## Railway

```bash
# Install Railway CLI: https://docs.railway.app/develop/cli
railway login
railway init

# Add PostgreSQL and Redis plugins
railway add --plugin postgresql
railway add --plugin redis

# Set environment variables
railway variables set JWT_SECRET=$(openssl rand -hex 32)

# Deploy
railway up
```

Config file: `deploy/railway/railway.toml`

---

## Heroku

```bash
# Install Heroku CLI
heroku create finmind-app
heroku stack:set container

# Add databases
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# Set secrets
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set GEMINI_API_KEY=your-key

# Deploy
cp deploy/heroku/heroku.yml .
git push heroku main
```

Review Apps: Enable in Heroku Pipeline, configured via `deploy/heroku/app.json`.

---

## Render

1. Fork the repo to your GitHub
2. Log in to [Render Dashboard](https://dashboard.render.com)
3. New → Blueprint → select your repo
4. Render auto-detects `deploy/render/render.yaml`
5. Fill in environment variables → Deploy

Or use the CLI:
```bash
render blueprint launch --file deploy/render/render.yaml
```

---

## Fly.io

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# Deploy backend
cd packages/backend
fly launch --name finmind-backend --no-deploy
fly secrets set JWT_SECRET=$(openssl rand -hex 32)
fly secrets set DATABASE_URL="postgres://..."
fly secrets set REDIS_URL="redis://..."
fly deploy --config ../../deploy/fly/fly.toml

# Deploy frontend
cd ../../app
fly launch --name finmind-frontend --no-deploy
fly deploy --config ../deploy/fly/fly-frontend.toml
```

> 💡 Fly.io offers free PostgreSQL (`fly postgres create`) and Upstash Redis (`fly redis create`)

---

## DigitalOcean App Platform

```bash
# Install doctl: https://docs.digitalocean.com/reference/doctl/
doctl auth init
doctl apps create --spec deploy/digitalocean/.do/app.yaml
```

Or in the DO console → Apps → Create App → From Spec, upload `deploy/digitalocean/.do/app.yaml`.

---

## DigitalOcean Droplet

One-click deploy to an Ubuntu Droplet (minimum 2 vCPU / 2 GB RAM):

```bash
# SSH into your Droplet and run
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/scripts/droplet-setup.sh | bash

# Or with a custom domain and SSL
FINMIND_DOMAIN=finmind.example.com CERTBOT_EMAIL=you@example.com bash droplet-setup.sh
```

The script automatically: installs Docker, configures firewall, clones the repo, generates secure secrets, starts services, and configures systemd auto-start.

---

## AWS ECS Fargate

```bash
# 1. Build and push images to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker build -t finmind-backend packages/backend/
docker tag finmind-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

# 2. Create Secrets Manager secret
aws secretsmanager create-secret --name finmind/jwt-secret --secret-string "$(openssl rand -hex 32)"

# 3. Register task definition
aws ecs register-task-definition --cli-input-json file://deploy/aws/ecs-task-definition.json

# 4. Create service
aws ecs create-service --cluster finmind --service-name finmind --task-definition finmind --desired-count 1 --launch-type FARGATE
```

Config file: `deploy/aws/ecs-task-definition.json`

---

## AWS App Runner

```bash
# After pushing image to ECR
aws apprunner create-service \
  --service-name finmind-backend \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": { "Port": "8000" }
    }
  }'
```

Config reference: `deploy/aws/apprunner.yaml`

---

## AWS CloudFormation

One-click deploy of the full infrastructure (ECS + RDS + ElastiCache + ALB):

```bash
aws cloudformation deploy \
  --template-file deploy/aws/cloudformation.yaml \
  --stack-name finmind \
  --parameter-overrides \
    VpcId=vpc-xxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    BackendImage=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest \
    FrontendImage=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-frontend:latest \
    JwtSecret=$(openssl rand -hex 32) \
    DBPassword=$(openssl rand -hex 16) \
  --capabilities CAPABILITY_IAM
```

---

## GCP Cloud Run

```bash
# 1. Enable APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com

# 2. Create Artifact Registry repo
gcloud artifacts repositories create finmind --repository-format=docker --location=us-central1

# 3. Create Secrets
echo -n "$(openssl rand -hex 32)" | gcloud secrets create finmind-jwt-secret --data-file=-
echo -n "postgresql://..." | gcloud secrets create finmind-database-url --data-file=-
echo -n "redis://..." | gcloud secrets create finmind-redis-url --data-file=-

# 4. Build and deploy
gcloud builds submit --config deploy/gcp/cloudbuild.yaml .

# Or deploy service.yaml directly
gcloud run services replace deploy/gcp/service.yaml --region us-central1
```

---

## Azure Container Apps

```bash
# 1. Create resource group and environment
az group create --name finmind-rg --location eastus
az containerapp env create --name finmind-env --resource-group finmind-rg --location eastus

# 2. Deploy using Bicep template
az deployment group create \
  --resource-group finmind-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    backendImage='ghcr.io/rohitdash08/finmind-backend:latest' \
    frontendImage='ghcr.io/rohitdash08/finmind-frontend:latest' \
    jwtSecret='YOUR_SECRET' \
    databaseUrl='postgresql://...' \
    redisUrl='redis://...'

# Or use Docker Compose compatible mode
az containerapp compose create \
  --resource-group finmind-rg \
  --environment finmind-env \
  --compose-file-path deploy/azure/azure-deploy.yaml
```

---

## Netlify (Frontend)

```bash
# Install Netlify CLI
npm i -g netlify-cli

# Deploy
cd app
netlify deploy --prod

# Or connect Git repo for auto-deploy
netlify init
```

> ⚠️ Set the `VITE_API_URL` environment variable to point to your backend URL

Config file: `deploy/netlify/netlify.toml`

---

## Vercel (Frontend)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd app
vercel --prod

# Or connect Git repo
vercel link
```

> ⚠️ Configure `VITE_API_URL` in Vercel project settings
> ⚠️ Update the API proxy URL in `deploy/vercel/vercel.json`

Config file: `deploy/vercel/vercel.json`

---

## Environment Variables Reference

All platforms require the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `JWT_SECRET` | ✅ | JWT signing secret (at least 32 characters) |
| `GEMINI_API_KEY` | ❌ | Google Gemini API key |
| `GEMINI_MODEL` | ❌ | Gemini model name (default: gemini-1.5-flash) |
| `LOG_LEVEL` | ❌ | Log level (default: INFO) |
| `VITE_API_URL` | ✅* | Backend API URL (required at frontend build time) |

---

## Database Migration

In all deployment methods, the backend automatically runs on startup:
```bash
python -m flask --app wsgi:app init-db
```

To run manually, exec into the backend container and run this command.
