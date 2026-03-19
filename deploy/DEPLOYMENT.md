# FinMind - Universal Deployment Guide

One-click deployment for FinMind across all major platforms.

## Quick Start

```bash
# One-command deployment (defaults to Docker Compose)
./deploy/scripts/deploy.sh

# Or specify a platform
./deploy/scripts/deploy.sh <platform>
```

## Supported Platforms

| Platform | Command | Type |
|----------|---------|------|
| Docker Compose | `./deploy/scripts/deploy.sh docker-compose` | Local |
| Kubernetes (Helm) | `./deploy/scripts/deploy.sh kubernetes` | Cloud-agnostic |
| Tilt | `./deploy/scripts/deploy.sh tilt` | Local K8s Dev |
| Railway | `./deploy/scripts/deploy.sh railway` | PaaS |
| Heroku | `./deploy/scripts/deploy.sh heroku` | PaaS |
| DigitalOcean App Platform | `./deploy/scripts/deploy.sh digitalocean` | PaaS |
| DigitalOcean Droplet | `./deploy/scripts/deploy.sh do-droplet` | VPS |
| Render | `./deploy/scripts/deploy.sh render` | PaaS |
| Fly.io | `./deploy/scripts/deploy.sh flyio` | PaaS |
| AWS ECS Fargate | `./deploy/scripts/deploy.sh aws-ecs` | Cloud |
| AWS App Runner | `./deploy/scripts/deploy.sh aws-apprunner` | Cloud |
| GCP Cloud Run | `./deploy/scripts/deploy.sh gcp` | Cloud |
| Azure Container Apps | `./deploy/scripts/deploy.sh azure` | Cloud |
| Netlify | `./deploy/scripts/deploy.sh netlify` | Frontend |
| Vercel | `./deploy/scripts/deploy.sh vercel` | Frontend |

---

## Docker Compose (Local Development)

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your values

# Start all services
./deploy/scripts/deploy.sh docker-compose

# Or directly:
docker compose up -d --build
```

**Services:**
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Nginx: http://localhost:8080
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

---

## Kubernetes (Helm Chart)

### Prerequisites
- kubectl configured with cluster access
- Helm 3.x installed

### Install

```bash
# Quick deploy
./deploy/scripts/deploy.sh kubernetes

# Or manually with Helm
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set secrets.jwtSecret="your-secret" \
  --set secrets.geminiApiKey="your-key" \
  --wait
```

### Features
- HorizontalPodAutoscaler (2-10 replicas for backend)
- NetworkPolicy (zero-trust networking)
- PodDisruptionBudget (high availability)
- TLS-ready Ingress with cert-manager
- Health probes (readiness + liveness)
- Prometheus scrape annotations
- ConfigMap/Secret separation

### Customization

```bash
# Override values
helm upgrade --install finmind deploy/helm/finmind \
  --set backend.replicaCount=3 \
  --set backend.autoscaling.maxReplicas=20 \
  --set ingress.hosts[0].host=finmind.yourdomain.com
```

---

## Tilt (Local K8s Development)

### Prerequisites
- Docker
- kubectl + local cluster (minikube, kind, or k3d)
- [Tilt](https://docs.tilt.dev/install.html)

### Start

```bash
# Start local cluster (if needed)
minikube start  # or: kind create cluster

# Start Tilt
./deploy/scripts/deploy.sh tilt
# Or: tilt up
```

### Features
- Live-reload for backend (gunicorn --reload syncs Python files)
- Live-reload for frontend (Vite HMR syncs src/ files)
- Proper dependency ordering: postgres -> redis -> backend -> frontend
- Port-forwarding for all services
- Manual test triggers in Tilt UI
- Resource grouping (app, data, monitoring, dev)

---

## Cloud Platforms

### Railway

```bash
# Install CLI: npm install -g @railway/cli
railway login
./deploy/scripts/deploy.sh railway
```

Config: `deploy/platforms/railway/railway.toml`

### Heroku

```bash
# Install CLI: https://devcenter.heroku.com/articles/heroku-cli
heroku login
heroku create finmind
./deploy/scripts/deploy.sh heroku
```

Config: `deploy/platforms/heroku/heroku.yml`, `deploy/platforms/heroku/app.json`

### DigitalOcean App Platform

```bash
# Install: https://docs.digitalocean.com/reference/doctl/how-to/install/
doctl auth init
./deploy/scripts/deploy.sh digitalocean
```

Config: `deploy/platforms/digitalocean/app-platform/do-app-spec.yaml`

### DigitalOcean Droplet

```bash
# Run on a fresh Ubuntu droplet:
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean/droplet/setup.sh | bash

# Or locally:
./deploy/scripts/deploy.sh do-droplet
```

### Render

```bash
./deploy/scripts/deploy.sh render
```

Blueprint: `deploy/platforms/render/render.yaml` - Connect via Render Dashboard.

### Fly.io

```bash
# Install: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
./deploy/scripts/deploy.sh flyio
```

Config: `deploy/platforms/flyio/backend/fly.toml`, `deploy/platforms/flyio/frontend/fly.toml`

### AWS ECS Fargate

```bash
export AWS_ACCOUNT_ID=123456789
export AWS_REGION=us-east-1
./deploy/scripts/deploy.sh aws-ecs
```

Config: `deploy/platforms/aws/ecs-fargate/task-definition.json`

### AWS App Runner

Config: `deploy/platforms/aws/app-runner/apprunner.yaml`

### GCP Cloud Run

```bash
export GCP_PROJECT_ID=your-project
./deploy/scripts/deploy.sh gcp
```

Config: `deploy/platforms/gcp/cloudrun.yaml`

### Azure Container Apps

```bash
export AZURE_RESOURCE_GROUP=finmind-rg
./deploy/scripts/deploy.sh azure
```

Config: `deploy/platforms/azure/container-app.yaml`

### Netlify (Frontend)

```bash
# Install: npm install -g netlify-cli
./deploy/scripts/deploy.sh netlify
```

Config: `deploy/platforms/netlify/netlify.toml`

### Vercel (Frontend)

```bash
# Install: npm install -g vercel
./deploy/scripts/deploy.sh vercel
```

Config: `deploy/platforms/vercel/vercel.json`

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | (auto) | PostgreSQL connection string |
| `REDIS_URL` | Yes | (auto) | Redis connection string |
| `JWT_SECRET` | Yes | `change-me` | JWT signing secret |
| `GEMINI_API_KEY` | No | - | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `VITE_API_URL` | Frontend | `http://localhost:8000` | Backend URL |

---

## Architecture

```
                    ┌─────────────┐
                    │   Ingress   │
                    │  (TLS/SSL)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │  Frontend  │ │ Nginx │ │ Monitoring│
        │  (React)   │ │(Proxy)│ │ (Grafana) │
        └───────────┘ └───┬───┘ └───────────┘
                          │
                    ┌─────▼─────┐
                    │  Backend  │
                    │  (Flask)  │
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              │                       │
        ┌─────▼─────┐         ┌──────▼─────┐
        │ PostgreSQL │         │   Redis    │
        │   (Data)   │         │  (Cache)   │
        └───────────┘         └────────────┘
```
