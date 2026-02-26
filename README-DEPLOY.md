# FinMind - Universal Deployment Guide

> One-click deployment for Docker, Kubernetes, Tilt, and 12+ cloud platforms.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Kubernetes Deployment (Helm)](#kubernetes-deployment-helm)
- [Tilt Local Development](#tilt-local-development)
- [Cloud Platform Deployments](#cloud-platform-deployments)
  - [Railway](#railway)
  - [Heroku](#heroku)
  - [DigitalOcean](#digitalocean)
  - [Render](#render)
  - [Fly.io](#flyio)
  - [AWS (ECS Fargate)](#aws-ecs-fargate)
  - [GCP Cloud Run](#gcp-cloud-run)
  - [Azure Container Apps](#azure-container-apps)
  - [Netlify (Frontend)](#netlify-frontend)
  - [Vercel (Frontend)](#vercel-frontend)
- [Environment Variables](#environment-variables)
- [Health Checks & Monitoring](#health-checks--monitoring)
- [TLS / HTTPS Setup](#tls--https-setup)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

The fastest way to get FinMind running:

```bash
# 1. Clone the repository
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind

# 2. Copy environment file and edit secrets
cp .env.example .env
# Edit .env with your actual secrets (JWT_SECRET, API keys, etc.)

# 3. One-click deploy (Docker Compose - development)
./deploy.sh docker --dev

# Or production mode:
./deploy.sh docker --prod --build

# Or Kubernetes via Helm:
./deploy.sh k8s --prod

# Or Tilt for local K8s development:
./deploy.sh tilt
```

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Nginx     │────▶│   Frontend   │     │  Prometheus   │
│  (Reverse   │     │  (React/Vite)│     │  + Grafana    │
│   Proxy)    │     └──────────────┘     └──────────────┘
│             │
│             │────▶┌──────────────┐     ┌──────────────┐
└─────────────┘     │   Backend    │────▶│  PostgreSQL   │
                    │  (Flask API) │     │   (Primary)   │
                    │              │────▶│──────────────│
                    └──────────────┘     │    Redis      │
                                        │   (Cache)     │
                                        └──────────────┘
```

| Component  | Technology       | Port  |
|-----------|-----------------|-------|
| Frontend  | React + Vite    | 80    |
| Backend   | Flask + Gunicorn| 8000  |
| Database  | PostgreSQL 16   | 5432  |
| Cache     | Redis 7         | 6379  |
| Proxy     | Nginx 1.27      | 80/443|
| Monitoring| Grafana         | 3000  |

---

## Prerequisites

| Tool       | Required For        | Install Link                                    |
|-----------|--------------------|-------------------------------------------------|
| Docker     | All Docker deploys  | https://docs.docker.com/get-docker/              |
| kubectl    | Kubernetes          | https://kubernetes.io/docs/tasks/tools/          |
| Helm 3     | K8s Helm charts     | https://helm.sh/docs/intro/install/              |
| Tilt       | Local K8s dev       | https://docs.tilt.dev/install.html               |
| Node 20+   | Frontend builds     | https://nodejs.org/                              |
| Python 3.11| Backend local dev   | https://www.python.org/                          |

---

## Docker Compose Deployment

### Development Mode

Includes hot-reload for both frontend and backend, plus full monitoring stack:

```bash
# Start all services
./deploy.sh docker --dev

# Or manually:
docker compose up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f frontend-dev
```

**Access points (dev):**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Nginx proxy: http://localhost:8080
- Grafana: http://localhost:3000 (admin / change-this-admin-password)
- Prometheus: http://localhost:9090

### Production Mode

Optimized images, resource limits, nginx reverse proxy with security headers:

```bash
# Build and deploy
./deploy.sh docker --prod --build

# Or manually:
docker compose -f docker-compose.prod.yml up -d --build
```

**Access points (prod):**
- Application: http://localhost (port 80)
- API via proxy: http://localhost/api
- Health check: http://localhost/health

### Useful Docker Commands

```bash
# Check service status
docker compose ps

# View resource usage
docker stats

# Scale backend
docker compose -f docker-compose.prod.yml up -d --scale backend=3

# Teardown (preserves volumes)
docker compose down

# Teardown (removes volumes - DATA LOSS)
docker compose down -v
```

---

## Kubernetes Deployment (Helm)

Full production-grade Kubernetes deployment with Helm charts, HPA autoscaling, health probes, and ingress.

### Quick Deploy

```bash
# Deploy to current K8s context
./deploy.sh k8s --prod

# Or manually with Helm:
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --wait
```

### Custom Values

Override defaults with your own values file:

```bash
# Create your overrides
cat > my-values.yaml << EOF
backend:
  replicaCount: 3
  image:
    repository: your-registry/finmind-backend
    tag: v1.2.3

ingress:
  hosts:
    - host: finmind.yourdomain.com
      paths:
        - path: /api
          pathType: Prefix
          service: backend
          port: 8000
        - path: /
          pathType: Prefix
          service: frontend
          port: 80
  tls:
    - secretName: finmind-tls
      hosts:
        - finmind.yourdomain.com

secrets:
  POSTGRES_PASSWORD: "your-strong-password"
  JWT_SECRET: "your-jwt-secret"
EOF

helm upgrade --install finmind deploy/helm/finmind \
  -f my-values.yaml \
  --namespace finmind
```

### Helm Chart Features

- **Autoscaling (HPA):** CPU/memory-based scaling (2-10 replicas by default)
- **Health probes:** Readiness + liveness on `/health` endpoint
- **Secret management:** Kubernetes Secrets for sensitive config
- **ConfigMaps:** Non-sensitive configuration separated
- **PVC:** Persistent storage for PostgreSQL
- **Ingress:** Path-based routing (frontend + backend on same domain)
- **Resource limits:** CPU/memory requests and limits on all pods

### Useful K8s Commands

```bash
# Check pod status
kubectl get pods -n finmind

# View backend logs
kubectl logs -f deploy/backend -n finmind

# Port-forward for local access
kubectl port-forward svc/backend 8000:8000 -n finmind
kubectl port-forward svc/frontend 5173:80 -n finmind

# Check HPA status
kubectl get hpa -n finmind

# Uninstall
helm uninstall finmind -n finmind
```

---

## Tilt Local Development

Tilt provides a fast inner-loop development experience on local Kubernetes with live code sync.

### Setup

```bash
# 1. Ensure local K8s is running (Docker Desktop / minikube / kind)
# For minikube:
minikube start --cpus=4 --memory=4096

# 2. Start Tilt
./deploy.sh tilt
# Or: tilt up
```

### What Tilt Provides

- **Live sync:** Backend Python changes sync instantly (no image rebuild)
- **Live sync:** Frontend source changes sync to container
- **Auto-rebuild:** Full rebuild only when dependencies change (requirements.txt, package.json)
- **Port forwards:** Backend (8000), Frontend (5173), PostgreSQL (5432), Redis (6379)
- **Web UI:** Dashboard at http://localhost:10350

### Tilt Commands

```bash
tilt up        # Start development environment
tilt down      # Tear down all resources
tilt ci        # CI mode (no interactive UI, exits on failure)
tilt trigger   # Manually trigger a resource rebuild
```

---

## Cloud Platform Deployments

### Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and initialize
railway login
railway init

# Link to project and deploy
railway link
railway up
```

Config: `deploy/platforms/railway/railway.json`

### Heroku

```bash
# Create app with addons
heroku create finmind-backend
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# Set secrets
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set LOG_LEVEL=INFO

# Deploy backend
git subtree push --prefix packages/backend heroku main
```

Config: `deploy/platforms/heroku/Procfile`

### DigitalOcean

**App Platform:**
```bash
doctl apps create --spec deploy/platforms/digitalocean/app-spec.yaml
```

**Droplet (manual):**
```bash
# SSH into droplet, clone repo, then:
./deploy.sh docker --prod --build
```

Config: `deploy/platforms/digitalocean/app-spec.yaml`

### Render

Connect your GitHub repo on [render.com](https://render.com) — it auto-detects the blueprint:

Config: `deploy/platforms/render/render.yaml`

### Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch (creates app + provisions resources)
fly launch --config deploy/platforms/flyio/fly.toml

# Create managed Postgres and Redis
fly postgres create --name finmind-db
fly postgres attach finmind-db
fly redis create --name finmind-redis

# Set secrets
fly secrets set JWT_SECRET=$(openssl rand -hex 32)

# Deploy
fly deploy
```

Config: `deploy/platforms/flyio/fly.toml`

### AWS (ECS Fargate)

```bash
# Build and push image to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker build -t finmind-backend packages/backend/
docker tag finmind-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

# Register task definition
aws ecs register-task-definition --cli-input-json file://deploy/platforms/aws/ecs-task-definition.json

# Create service
aws ecs create-service \
  --cluster finmind-cluster \
  --service-name finmind-backend \
  --task-definition finmind-backend \
  --desired-count 2 \
  --launch-type FARGATE
```

Config: `deploy/platforms/aws/ecs-task-definition.json`

### GCP Cloud Run

```bash
# Build and push to GCR
gcloud builds submit --tag gcr.io/PROJECT_ID/finmind-backend packages/backend/

# Deploy service
gcloud run services replace deploy/platforms/gcp/cloudrun-service.yaml

# Or quick deploy:
gcloud run deploy finmind-backend \
  --image gcr.io/PROJECT_ID/finmind-backend \
  --port 8000 \
  --region us-central1 \
  --allow-unauthenticated
```

Config: `deploy/platforms/gcp/cloudrun-service.yaml`

### Azure Container Apps

```bash
# Create resource group and environment
az group create --name finmind-rg --location eastus
az containerapp env create --name finmind-env --resource-group finmind-rg

# Build and push to ACR
az acr build --registry finmindacr --image finmind-backend:latest packages/backend/

# Deploy
az containerapp create --yaml deploy/platforms/azure/container-app.yaml \
  --resource-group finmind-rg
```

Config: `deploy/platforms/azure/container-app.yaml`

### Netlify (Frontend)

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
cd app
netlify init
netlify deploy --prod
```

Or connect GitHub repo on [netlify.com](https://netlify.com) — auto-detects config.

Config: `deploy/platforms/netlify/netlify.toml`

### Vercel (Frontend)

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
cd app
vercel --prod
```

Or connect GitHub repo on [vercel.com](https://vercel.com).

Config: `deploy/platforms/vercel/vercel.json`

---

## Environment Variables

| Variable             | Required | Default                    | Description                    |
|---------------------|----------|----------------------------|--------------------------------|
| `DATABASE_URL`       | Yes      | (composed from PG vars)    | PostgreSQL connection string   |
| `REDIS_URL`          | Yes      | `redis://redis:6379/0`     | Redis connection string        |
| `POSTGRES_USER`      | Yes      | `finmind`                  | PostgreSQL username            |
| `POSTGRES_PASSWORD`  | Yes      | —                          | PostgreSQL password            |
| `POSTGRES_DB`        | Yes      | `finmind`                  | PostgreSQL database name       |
| `JWT_SECRET`         | Yes      | —                          | JWT signing secret             |
| `OPENAI_API_KEY`     | No       | —                          | OpenAI API key                 |
| `GEMINI_API_KEY`     | No       | —                          | Google Gemini API key          |
| `GEMINI_MODEL`       | No       | `gemini-1.5-flash`         | Gemini model name              |
| `VITE_API_URL`       | Yes      | `http://localhost:8000`    | Backend URL for frontend       |
| `LOG_LEVEL`          | No       | `INFO`                     | Logging level                  |
| `GUNICORN_WORKERS`   | No       | `2`                        | Gunicorn worker processes      |
| `GUNICORN_THREADS`   | No       | `4`                        | Gunicorn threads per worker    |

---

## Health Checks & Monitoring

### Endpoints

| Endpoint        | Description              |
|----------------|--------------------------|
| `/health`       | Backend health check     |
| `/nginx-health` | Nginx proxy health       |
| `/nginx_status` | Nginx stub status        |

### Monitoring Stack (Docker Compose dev)

- **Prometheus** (`:9090`): Metrics collection
- **Grafana** (`:3000`): Dashboards and visualization
- **Loki + Promtail**: Log aggregation
- **Exporters**: Node, PostgreSQL, Redis, Nginx metrics

### Kubernetes Observability

The Helm chart includes:
- Readiness probes on all application pods
- Liveness probes with appropriate thresholds
- Resource requests/limits for proper scheduling
- HPA metrics (CPU + memory utilization)

---

## TLS / HTTPS Setup

### Docker Compose (Production)

Place your certificates in `deploy/nginx/ssl/`:

```bash
deploy/nginx/ssl/
├── cert.pem      # Your TLS certificate
└── key.pem       # Your private key
```

### Kubernetes

Use cert-manager for automatic TLS:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# Update values.yaml with TLS config
ingress:
  tls:
    - secretName: finmind-tls
      hosts:
        - finmind.yourdomain.com
```

---

## Troubleshooting

### Common Issues

**Backend won't start:**
```bash
# Check logs
docker compose logs backend
# Or K8s:
kubectl logs -f deploy/backend -n finmind

# Common fix: ensure PostgreSQL is healthy first
docker compose ps postgres
```

**Database connection refused:**
```bash
# Verify PostgreSQL is running and healthy
docker compose exec postgres pg_isready -U finmind

# Check DATABASE_URL format
# Correct: postgresql+psycopg2://user:pass@host:5432/dbname
```

**Frontend can't reach backend:**
```bash
# Verify VITE_API_URL is set correctly
# In Docker: should point to backend service name
# In production: should point to your domain/API URL
```

**Kubernetes pods in CrashLoopBackOff:**
```bash
# Check events
kubectl describe pod <pod-name> -n finmind

# Check logs from previous crash
kubectl logs <pod-name> -n finmind --previous
```

**Tilt errors:**
```bash
# Ensure local K8s is running
kubectl cluster-info

# Reset Tilt state
tilt down && tilt up
```

---

## Project Structure

```
FinMind/
├── deploy.sh                    # One-click deployment script
├── Tiltfile                     # Tilt local K8s development
├── docker-compose.yml           # Development compose
├── docker-compose.prod.yml      # Production compose
├── app/                         # Frontend (React/Vite)
│   ├── Dockerfile               # Multi-stage frontend build
│   └── nginx.conf               # SPA nginx config
├── packages/backend/            # Backend (Flask)
│   ├── Dockerfile               # Multi-stage backend build
│   └── requirements.txt
├── deploy/
│   ├── nginx/
│   │   └── nginx-prod.conf      # Production reverse proxy
│   ├── helm/finmind/            # Helm chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       ├── _helpers.tpl
│   │       ├── namespace.yaml
│   │       ├── configmap-secrets.yaml
│   │       ├── postgresql.yaml
│   │       ├── redis.yaml
│   │       ├── backend.yaml
│   │       ├── frontend.yaml
│   │       ├── hpa.yaml
│   │       └── ingress.yaml
│   ├── tilt/
│   │   └── values-dev.yaml      # Tilt dev overrides
│   ├── k8s/                     # Raw K8s manifests
│   └── platforms/               # Cloud platform configs
│       ├── railway/
│       ├── heroku/
│       ├── render/
│       ├── flyio/
│       ├── digitalocean/
│       ├── aws/
│       ├── gcp/
│       ├── azure/
│       ├── netlify/
│       └── vercel/
└── monitoring/                  # Grafana, Prometheus, Loki
```

---

## License

This deployment configuration is part of the [FinMind](https://github.com/rohitdash08/FinMind) project. See [LICENSE](LICENSE) for details.
