# FinMind — Universal Deployment Guide

Production-grade deployment guide covering Docker, Kubernetes (Helm), Tilt, and 12+ cloud platforms.

## Quick Start

```bash
# One command — pick your platform:
./deploy/scripts/deploy.sh <platform>

# Examples:
./deploy/scripts/deploy.sh docker-compose   # Local development
./deploy/scripts/deploy.sh kubernetes       # Production K8s via Helm
./deploy/scripts/deploy.sh tilt             # Local K8s with hot-reload
./deploy/scripts/deploy.sh flyio            # Fly.io
./deploy/scripts/deploy.sh gcp-cloudrun     # GCP Cloud Run
```

## Architecture

```
                     ┌──────────────┐
                     │   Ingress    │
                     │  (TLS/HTTPS) │
                     └──────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────┴─────┐ ┌────┴────┐ ┌─────┴─────┐
        │ Frontend  │ │  Nginx  │ │  Grafana  │
        │ (React)   │ │ (Proxy) │ │ (Monitor) │
        │ Port 80   │ │ Port 80 │ │ Port 3000 │
        └───────────┘ └────┬────┘ └───────────┘
                           │
                     ┌─────┴─────┐
                     │  Backend  │
                     │ (Flask)   │
                     │ Port 8000 │
                     └─────┬─────┘
                           │
              ┌────────────┼────────────┐
              │                         │
        ┌─────┴─────┐           ┌──────┴──────┐
        │ PostgreSQL │           │    Redis    │
        │ Port 5432  │           │  Port 6379  │
        └────────────┘           └─────────────┘
```

## Table of Contents

- [Docker Compose (Local Development)](#docker-compose-local-development)
- [Kubernetes via Helm](#kubernetes-via-helm)
- [Tilt (Local K8s Dev)](#tilt-local-k8s-dev)
- [Railway](#railway)
- [Heroku](#heroku)
- [Render](#render)
- [Fly.io](#flyio)
- [DigitalOcean App Platform](#digitalocean-app-platform)
- [DigitalOcean Droplet](#digitalocean-droplet)
- [AWS ECS Fargate](#aws-ecs-fargate)
- [AWS App Runner](#aws-app-runner)
- [GCP Cloud Run](#gcp-cloud-run)
- [Azure Container Apps](#azure-container-apps)
- [Netlify (Frontend)](#netlify-frontend)
- [Vercel (Frontend)](#vercel-frontend)
- [Smoke Tests](#smoke-tests)
- [Troubleshooting](#troubleshooting)

---

## Docker Compose (Local Development)

The simplest way to run FinMind locally.

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start all services
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/health
open http://localhost:5173
```

**Services:**
| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

---

## Kubernetes via Helm

Production-grade deployment with autoscaling, TLS, network policies, and observability.

### Prerequisites
- `kubectl` connected to a cluster
- `helm` v3+

### Deploy

```bash
# Default installation
helm upgrade --install finmind deploy/helm/finmind \
    --namespace finmind --create-namespace --wait

# Production with custom values
helm upgrade --install finmind deploy/helm/finmind \
    --namespace finmind --create-namespace \
    --set secrets.jwtSecret=$(openssl rand -hex 32) \
    --set secrets.postgresPassword=$(openssl rand -hex 16) \
    --set ingress.hosts[0].host=finmind.yourdomain.com \
    --set ingress.tls[0].hosts[0]=finmind.yourdomain.com \
    --wait --timeout 5m
```

### What's Included
- **HorizontalPodAutoscaler**: Backend 2-10 replicas, Frontend 2-6 replicas
- **PodDisruptionBudget**: Guarantees availability during rolling updates
- **NetworkPolicy**: Zero-trust — only authorized pods can communicate
- **Ingress with TLS**: cert-manager integration for automatic HTTPS
- **Health probes**: Readiness + liveness on all services
- **Init containers**: Wait for dependencies, auto-run DB migrations
- **Prometheus annotations**: Backend pods are scrape-ready
- **ConfigMap checksums**: Pods restart automatically when config changes

### Helm Values Override

```bash
# See all configurable values
helm show values deploy/helm/finmind

# Example: production-values.yaml
cat <<EOF > production-values.yaml
secrets:
  postgresPassword: "super-secure-password"
  jwtSecret: "long-random-secret"
backend:
  autoscaling:
    minReplicas: 3
    maxReplicas: 20
ingress:
  hosts:
    - host: finmind.company.com
      paths:
        - path: /
          pathType: Prefix
          service: frontend
          port: 80
EOF

helm upgrade --install finmind deploy/helm/finmind -f production-values.yaml
```

---

## Tilt (Local K8s Dev)

Best for development — live-reload for both backend (Python) and frontend (React/Vite).

### Prerequisites
- Docker Desktop with Kubernetes enabled, or minikube/kind
- [Tilt](https://docs.tilt.dev/install.html)

### Run

```bash
tilt up
```

**Features:**
- Backend: Python file sync + gunicorn `--reload` (no rebuild needed)
- Frontend: Vite HMR via file sync (instant updates)
- Dependency ordering: postgres -> redis -> backend -> frontend
- Port forwarding: Backend on :8000, Frontend on :5173
- Manual trigger buttons: Run tests, smoke tests from Tilt UI
- Resource grouping: app, data, dev categories

### Tilt UI

Open http://localhost:10350 to see:
- Build/deploy status for all services
- Live logs
- Manual action buttons (run tests, smoke tests)

---

## Railway

```bash
./deploy/scripts/deploy.sh railway
```

Or manually:
1. Fork this repo
2. Go to [railway.app](https://railway.app)
3. New Project -> Deploy from GitHub
4. Add PostgreSQL and Redis plugins
5. Railway auto-detects `deploy/platforms/railway/railway.toml`

---

## Heroku

```bash
./deploy/scripts/deploy.sh heroku
```

Or one-click deploy (after pushing `app.json` to repo root):
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

Config: `deploy/platforms/heroku/app.json`, `deploy/platforms/heroku/heroku.yml`

---

## Render

```bash
./deploy/scripts/deploy.sh render
```

Or use Render Blueprint:
1. Go to [render.com/blueprints](https://dashboard.render.com/blueprints)
2. Connect this repo
3. Render auto-provisions backend, frontend, PostgreSQL, and Redis

Blueprint: `deploy/platforms/render/render.yaml`

---

## Fly.io

```bash
./deploy/scripts/deploy.sh flyio
```

Deploys both backend and frontend as separate Fly apps with health checks and auto-scaling.

Config: `deploy/platforms/flyio/backend/fly.toml`, `deploy/platforms/flyio/frontend/fly.toml`

---

## DigitalOcean App Platform

```bash
./deploy/scripts/deploy.sh digitalocean
```

Or via CLI:
```bash
doctl apps create --spec deploy/platforms/digitalocean/app-platform/do-app-spec.yaml
```

Includes managed PostgreSQL 16 and Redis 7.

---

## DigitalOcean Droplet

One-line install on a fresh Ubuntu droplet:

```bash
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean/droplet/setup.sh | sudo bash
```

Installs Docker, clones the repo, generates secure secrets, and starts everything.

---

## AWS ECS Fargate

```bash
./deploy/scripts/deploy.sh aws-ecs
```

Prerequisites: AWS CLI configured, ECR repository, ECS cluster.

The script:
1. Builds and pushes to ECR
2. Registers task definition with SSM Parameter Store secrets
3. Deploys to ECS Fargate

Config: `deploy/platforms/aws/ecs-fargate/task-definition.json`

---

## AWS App Runner

```bash
./deploy/scripts/deploy.sh aws-apprunner
```

Simplest AWS option — auto-scaling with zero infrastructure management.

Config: `deploy/platforms/aws/app-runner/apprunner.yaml`

---

## GCP Cloud Run

```bash
export GCP_PROJECT_ID=your-project-id
./deploy/scripts/deploy.sh gcp-cloudrun
```

The script:
1. Enables required GCP APIs
2. Builds with Cloud Build
3. Creates Cloud SQL PostgreSQL + Memorystore Redis
4. Deploys to Cloud Run with Secret Manager integration

Config: `deploy/platforms/gcp/cloudrun.yaml`

---

## Azure Container Apps

```bash
./deploy/scripts/deploy.sh azure
```

The script:
1. Creates resource group + Azure Container Registry
2. Builds and pushes image via ACR
3. Creates Container Apps environment
4. Provisions Azure Database for PostgreSQL + Azure Cache for Redis
5. Deploys with auto-scaling (1-10 replicas)

Config: `deploy/platforms/azure/container-app.yaml`

---

## Netlify (Frontend)

```bash
./deploy/scripts/deploy.sh netlify
```

Features: SPA fallback, API proxy, security headers, static asset caching.

Config: `deploy/platforms/netlify/netlify.toml`

---

## Vercel (Frontend)

```bash
./deploy/scripts/deploy.sh vercel
```

Features: SPA rewrites, security headers, asset caching.

Config: `deploy/platforms/vercel/vercel.json`

---

## Smoke Tests

Validate any running deployment against the acceptance criteria:

```bash
# Test local deployment
./deploy/scripts/smoke-test.sh http://localhost:8000 http://localhost:5173

# Test remote deployment
./deploy/scripts/smoke-test.sh https://api.finmind.example.com https://finmind.example.com
```

**Checks:**
1. Frontend reachable (HTTP 200)
2. Backend health endpoint responsive
3. Database connectivity (via /health)
4. Auth endpoints responsive (register, login)
5. Core module endpoints exist (expenses, bills, reminders, dashboard, insights)

---

## Troubleshooting

### Docker Compose: Backend won't start
```bash
# Check logs
docker compose logs backend

# Verify postgres is healthy
docker compose exec postgres pg_isready -U finmind

# Re-run DB init
docker compose exec backend python -m flask --app wsgi:app init-db
```

### Kubernetes: Pods in CrashLoopBackOff
```bash
# Check pod logs
kubectl logs -n finmind deployment/backend --previous

# Check events
kubectl get events -n finmind --sort-by=.metadata.creationTimestamp

# Verify secrets
kubectl get secret finmind-secrets -n finmind -o yaml
```

### Helm: Upgrade fails
```bash
# Check release status
helm status finmind -n finmind

# Rollback
helm rollback finmind -n finmind

# Full reinstall
helm uninstall finmind -n finmind
helm install finmind deploy/helm/finmind -n finmind --create-namespace
```

### Tilt: Images not building
```bash
# Verify local K8s context
kubectl config current-context

# Restart Tilt
tilt down && tilt up
```
