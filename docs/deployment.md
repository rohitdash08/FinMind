# FinMind — Universal Deployment Guide

> One-click (or one-command) deployment across 15 platforms: Docker, Kubernetes (raw + Helm + Tilt), Railway, Heroku, Render, Fly.io, DigitalOcean (App Platform + Droplet), AWS ECS Fargate, GCP Cloud Run, Azure Container Apps, Netlify, and Vercel.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Platform Guides](#platform-guides)
  - [Docker Compose](#docker-compose)
  - [Kubernetes](#kubernetes)
  - [Helm](#helm)
  - [Tilt (Local K8s Dev)](#tilt)
  - [Railway](#railway)
  - [Heroku](#heroku)
  - [Render](#render)
  - [Fly.io](#flyio)
  - [DigitalOcean App Platform](#digitalocean-app-platform)
  - [DigitalOcean Droplet](#digitalocean-droplet)
  - [AWS ECS Fargate](#aws-ecs-fargate)
  - [GCP Cloud Run](#gcp-cloud-run)
  - [Azure Container Apps](#azure-container-apps)
  - [Netlify (Frontend)](#netlify)
  - [Vercel (Frontend)](#vercel)
- [Environment Variables](#environment-variables)
- [Health Checks](#health-checks)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind

# Copy environment file
cp .env.example .env
# Edit .env with your values

# Deploy to any platform:
./deploy.sh docker          # Local Docker Compose
./deploy.sh helm            # Kubernetes via Helm
./deploy.sh tilt            # Local K8s dev with Tilt
./deploy.sh railway         # Railway PaaS
./deploy.sh fly             # Fly.io
# ... see ./deploy.sh --list for all options
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│    Nginx     │────▶│   Backend    │
│  React/Vite  │     │  (reverse    │     │  Flask/      │
│  Port: 80    │     │   proxy)     │     │  Gunicorn    │
└─────────────┘     └──────────────┘     │  Port: 8000  │
                                          └──────┬───────┘
                                                 │
                              ┌──────────────────┼──────────────────┐
                              │                  │                  │
                        ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
                        │ PostgreSQL │     │   Redis   │     │   AI     │
                        │  Port:5432 │     │ Port:6379 │     │ Services │
                        └───────────┘     └───────────┘     │ (Gemini/ │
                                                             │ OpenAI)  │
                                                             └──────────┘
```

**Services:**
| Service | Technology | Port | Description |
|---------|-----------|------|-------------|
| Frontend | React + Vite + Nginx | 80 | SPA with expense tracking UI |
| Backend | Python Flask + Gunicorn | 8000 | REST API server |
| PostgreSQL | PostgreSQL 16 | 5432 | Primary database |
| Redis | Redis 7 | 6379 | Cache and session store |
| Nginx | Nginx 1.27 | 8080 | Reverse proxy (Docker Compose) |

---

## Prerequisites

- Docker 20+ and Docker Compose v2
- For Kubernetes: `kubectl` configured, cluster access
- For Tilt: [Tilt](https://docs.tilt.dev/install.html) + local K8s (Docker Desktop/minikube/kind)
- For Helm: Helm 3.x
- Platform CLI tools as needed (see individual guides)

---

## Platform Guides

### Docker Compose

The simplest deployment path. Includes full monitoring stack (Prometheus, Grafana, Loki).

```bash
cp .env.example .env
# Edit .env with production values
docker compose up -d --build
```

**Endpoints:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Backend (via Nginx): http://localhost:8080
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

**Teardown:**
```bash
docker compose down -v  # -v removes volumes
```

---

### Kubernetes

Raw Kubernetes manifests for any cluster.

```bash
# Create namespace and secrets
kubectl apply -f deploy/k8s/namespace.yaml

# Create secrets (edit with your values first)
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit deploy/k8s/secrets.yaml with base64-encoded values
kubectl apply -f deploy/k8s/secrets.yaml

# Deploy application stack
kubectl apply -f deploy/k8s/app-stack.yaml

# Deploy monitoring stack (optional)
kubectl apply -f deploy/k8s/monitoring-stack.yaml

# Verify
kubectl get pods -n finmind
```

**Port forwarding for local access:**
```bash
kubectl port-forward -n finmind svc/backend 8000:8000
kubectl port-forward -n finmind svc/nginx 8080:80
```

---

### Helm

Production-grade Helm chart with TLS, HPA, and observability.

```bash
# Install with defaults
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace

# Install with custom values
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set secrets.jwtSecret=my-secret \
  --set secrets.geminiApiKey=my-key \
  --set ingress.hosts[0].host=finmind.example.com \
  --set ingress.tls[0].secretName=finmind-tls

# Or use a values file
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  -f my-values.yaml
```

**Features:**
- TLS via cert-manager (auto Let's Encrypt)
- HPA: backend scales 2→8 pods on CPU/memory
- Health probes on all containers
- Prometheus scrape annotations
- Resource requests/limits
- Init containers wait for DB/Redis

**Uninstall:**
```bash
helm uninstall finmind -n finmind
```

---

### Tilt

Local Kubernetes development with live-reload.

```bash
# Prerequisites: Docker Desktop with K8s enabled (or minikube/kind)
# Install Tilt: https://docs.tilt.dev/install.html

tilt up
```

**Dashboard:** http://localhost:10350

**Port forwards (automatic):**
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

**Features:**
- Live code sync (no rebuild needed for Python/React changes)
- Automatic dependency ordering (DB → Redis → Backend → Frontend)
- Manual tasks: `db-seed`, `run-tests` (trigger from Tilt dashboard)

**Teardown:**
```bash
tilt down
```

---

### Railway

```bash
# Option 1: Deploy button
# Click the "Deploy on Railway" button in the README

# Option 2: CLI
npm install -g @railway/cli
railway login
railway link
railway up
```

Config: `deploy/railway/railway.json`

---

### Heroku

```bash
# Option 1: Heroku Button
# Click: https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind

# Option 2: CLI
heroku create finmind-app
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
heroku stack:set container
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
git push heroku main
```

Config: `deploy/heroku/heroku.yml`, `deploy/heroku/app.json`

---

### Render

```bash
# Blueprint deployment (recommended)
# 1. Go to https://render.com/deploy
# 2. Connect your GitHub repo
# 3. Render auto-detects deploy/render/render.yaml
```

Config: `deploy/render/render.yaml`

---

### Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh
fly auth login

# Deploy (creates apps, databases, and deploys)
./deploy.sh fly
# or directly:
bash deploy/fly/deploy.sh
```

Config: `deploy/fly/fly.backend.toml`, `deploy/fly/fly.frontend.toml`

---

### DigitalOcean App Platform

```bash
# Option 1: CLI
doctl apps create --spec deploy/digitalocean/app-spec.yaml

# Option 2: Dashboard
# Import deploy/digitalocean/app-spec.yaml in DO dashboard
```

Config: `deploy/digitalocean/app-spec.yaml`

---

### DigitalOcean Droplet

```bash
# On a fresh Ubuntu 22.04 droplet:
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/droplet-setup.sh | bash
```

Includes: Docker, UFW firewall, fail2ban, systemd service, log rotation.

Config: `deploy/digitalocean/droplet-setup.sh`

---

### AWS ECS Fargate

```bash
# Prerequisites: AWS CLI configured, VPC with subnets
./deploy.sh aws

# Or step-by-step:
bash deploy/aws/deploy.sh
```

Creates: ECR repos, ECS cluster, task definition, ALB, auto-scaling (2-10 tasks), CloudWatch logging.

Config: `deploy/aws/ecs-task-definition.json`, `deploy/aws/ecs-service.json`

---

### GCP Cloud Run

```bash
# Prerequisites: gcloud CLI configured, project selected
./deploy.sh gcp

# Or step-by-step:
bash deploy/gcp/deploy.sh
```

Creates: Cloud SQL PostgreSQL, Memorystore Redis, VPC connector, Secret Manager entries, Cloud Run services.

Config: `deploy/gcp/cloudbuild.yaml`, `deploy/gcp/deploy.sh`

---

### Azure Container Apps

```bash
# Prerequisites: Azure CLI configured
./deploy.sh azure

# Or step-by-step:
bash deploy/azure/deploy.sh

# Or use Bicep IaC:
az deployment group create \
  --resource-group finmind-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters appName=finmind
```

Config: `deploy/azure/deploy.sh`, `deploy/azure/bicep/main.bicep`

---

### Netlify

Frontend-only deployment. Backend must be hosted separately.

```bash
# 1. Connect repo in Netlify dashboard
# 2. Settings:
#    Base directory: app
#    Build command: npm run build
#    Publish directory: app/dist
# 3. Environment variables:
#    VITE_API_URL = https://your-backend-url

# Or CLI:
cd app && netlify deploy --prod
```

Config: `deploy/netlify/netlify.toml`

---

### Vercel

Frontend-only deployment. Backend must be hosted separately.

```bash
# 1. Import project in Vercel dashboard
# 2. Root directory: app
# 3. Framework: Vite
# 4. Environment variables:
#    VITE_API_URL = https://your-backend-url

# Or CLI:
cd app && vercel --prod
```

Config: `deploy/vercel/vercel.json`

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET` | Yes | — | Secret for JWT token signing |
| `POSTGRES_USER` | Yes | `finmind` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | — | PostgreSQL password |
| `POSTGRES_DB` | Yes | `finmind` | PostgreSQL database name |
| `GEMINI_API_KEY` | No | — | Google Gemini API key (AI features) |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name |
| `OPENAI_API_KEY` | No | — | OpenAI API key (AI features) |
| `LOG_LEVEL` | No | `INFO` | Python log level |
| `SMTP_URL` | No | — | SMTP URL for email reminders |
| `EMAIL_FROM` | No | — | Sender email address |
| `TWILIO_ACCOUNT_SID` | No | — | Twilio SID (WhatsApp) |
| `TWILIO_AUTH_TOKEN` | No | — | Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | No | — | Twilio WhatsApp number |

---

## Health Checks

| Endpoint | Port | Expected | Description |
|----------|------|----------|-------------|
| `GET /health` | 8000 | `{"status":"ok"}` 200 | Backend health |
| `GET /metrics` | 8000 | Prometheus format | Prometheus metrics |
| `GET /` | 80 | HTML 200 | Frontend reachable |

All deployment configs use these endpoints for readiness/liveness probes.

---

## Monitoring

The Docker Compose and Kubernetes deployments include a full monitoring stack:

- **Prometheus** — Metrics collection (port 9090)
- **Grafana** — Dashboards and alerting (port 3000)
- **Loki** — Log aggregation (port 3100)
- **Promtail** — Log shipping to Loki
- **Exporters** — PostgreSQL, Redis, Nginx metrics

Default Grafana login: `finmind_admin` / (see `GRAFANA_ADMIN_PASSWORD` in `.env`)

---

## Troubleshooting

### Backend can't connect to PostgreSQL
```bash
# Docker Compose: check if postgres is healthy
docker compose ps
docker compose logs postgres

# Kubernetes: check pod status
kubectl get pods -n finmind
kubectl logs -n finmind deploy/postgres
```

### Frontend shows blank page
- Ensure `VITE_API_URL` points to the correct backend URL
- Check browser console for CORS errors
- For PaaS: ensure frontend and backend are on the same domain or CORS is configured

### Database migrations
```bash
# Docker: run init-db
docker compose exec backend python -m flask --app wsgi:app init-db

# Kubernetes:
kubectl exec -n finmind deploy/backend -- python -m flask --app wsgi:app init-db
```

### View logs
```bash
# Docker
docker compose logs -f backend

# Kubernetes
kubectl logs -n finmind deploy/backend -f

# Tilt: check http://localhost:10350
```
