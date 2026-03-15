# FinMind — Universal Deployment Guide

Complete deployment documentation for running FinMind on any platform.

## Architecture

```
                          +------------------+
                          |   Load Balancer  |
                          |  (nginx / cloud) |
                          +--------+---------+
                                   |
                     +-------------+-------------+
                     |                           |
              +------+------+            +------+------+
              |   Frontend  |            |   Backend   |
              | React + nginx|           | Flask/Gunicorn|
              |   (port 80) |            |  (port 8000) |
              +------+------+            +------+------+
                     |                           |
                     |              +------------+------------+
                     |              |                         |
                     |       +------+------+          +------+------+
                     |       | PostgreSQL  |          |    Redis    |
                     |       |   (5432)    |          |   (6379)   |
                     |       +-------------+          +-------------+
                     |
              Serves static
              assets (SPA)

    Request Flow:
    Browser --> /            --> Frontend (React SPA)
    Browser --> /api/*       --> Backend (Flask API)
    Browser --> /health      --> Backend health check
    Browser --> /metrics     --> Prometheus metrics
```

## Table of Contents

1. [Quick Start](#quick-start)
2. [Environment Variables](#environment-variables)
3. [Docker Compose](#docker-compose)
4. [Kubernetes (Helm)](#kubernetes-helm)
5. [Tilt (Local K8s Dev)](#tilt-local-k8s-dev)
6. [Railway](#railway)
7. [Render](#render)
8. [Fly.io](#flyio)
9. [Heroku](#heroku)
10. [DigitalOcean](#digitalocean)
11. [AWS (ECS Fargate / App Runner)](#aws)
12. [GCP Cloud Run](#gcp-cloud-run)
13. [Azure Container Apps](#azure-container-apps)
14. [Netlify (Frontend)](#netlify-frontend)
15. [Vercel (Frontend)](#vercel-frontend)
16. [Troubleshooting](#troubleshooting)

---

## Quick Start

The fastest way to run FinMind locally:

```bash
# Clone and enter the repo
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind

# Run the setup script
chmod +x deploy/scripts/setup-local.sh
./deploy/scripts/setup-local.sh --docker
```

Or deploy to any platform with the unified script:

```bash
chmod +x deploy/scripts/deploy.sh
./deploy/scripts/deploy.sh --platform <platform> --env .env
```

---

## Environment Variables

All configuration is done via environment variables. Copy `.env.example` to `.env` and edit:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+psycopg2://finmind:finmind@postgres:5432/finmind` | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET` | Yes | `change-me` | Secret key for JWT token signing. **Must be changed in production.** |
| `POSTGRES_USER` | Yes | `finmind` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | `finmind` | PostgreSQL password. **Must be changed in production.** |
| `POSTGRES_DB` | Yes | `finmind` | PostgreSQL database name |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `GEMINI_API_KEY` | No | `""` | Google Gemini API key for AI insights |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model identifier |
| `OPENAI_API_KEY` | No | `""` | OpenAI API key (alternative AI provider) |
| `TWILIO_ACCOUNT_SID` | No | `""` | Twilio account SID for WhatsApp notifications |
| `TWILIO_AUTH_TOKEN` | No | `""` | Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | No | `""` | Twilio WhatsApp sender number |
| `EMAIL_FROM` | No | `""` | Sender email for notifications |
| `SMTP_URL` | No | `""` | SMTP connection URL (e.g., `smtp+ssl://user:pass@mail:465`) |
| `VITE_API_URL` | No | `http://localhost:8000` | Backend URL (build-time, baked into frontend) |
| `GUNICORN_WORKERS` | No | `2` | Number of Gunicorn worker processes |
| `GUNICORN_THREADS` | No | `4` | Threads per Gunicorn worker |

---

## Docker Compose

Production-ready Docker Compose deployment with health checks, resource limits, and a reverse proxy.

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with production values (strong passwords, real JWT secret)

# 2. Build and start
docker compose -f deploy/docker/docker-compose.prod.yml --env-file .env up -d --build

# 3. Verify
curl http://localhost/health    # Backend health
curl http://localhost           # Frontend
```

**Files:**
- `deploy/docker/docker-compose.prod.yml` — Production compose file
- `deploy/docker/backend.Dockerfile` — Multi-stage backend image
- `deploy/docker/frontend.Dockerfile` — Multi-stage frontend image
- `deploy/docker/nginx-proxy.conf` — Reverse proxy config
- `deploy/docker/nginx.conf` — Frontend nginx config

**Stopping:**
```bash
docker compose -f deploy/docker/docker-compose.prod.yml down
# To also remove volumes (data):
docker compose -f deploy/docker/docker-compose.prod.yml down -v
```

---

## Kubernetes (Helm)

Full Helm chart with deployments, services, ingress, HPA, PVCs, health probes, and TLS.

### Prerequisites
- `kubectl` configured to connect to your cluster
- `helm` v3 installed
- An Ingress Controller (e.g., nginx-ingress) installed in the cluster
- cert-manager installed (for automatic TLS)

### Deploy

```bash
# Install with required secrets
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set secrets.POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --set secrets.JWT_SECRET="$(openssl rand -hex 32)" \
  --set ingress.hosts[0].host=finmind.yourdomain.com \
  --set ingress.tls[0].hosts[0]=finmind.yourdomain.com

# Check status
kubectl get pods -n finmind
kubectl get ingress -n finmind
```

### Custom Values

Create a `values-prod.yaml` to override defaults:

```yaml
backend:
  replicaCount: 3
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: "2"
      memory: 1Gi

ingress:
  hosts:
    - host: finmind.yourdomain.com
      paths:
        - path: /
          pathType: Prefix
          service: frontend
        - path: /api
          pathType: Prefix
          service: backend
```

```bash
helm upgrade --install finmind deploy/helm/finmind -f values-prod.yaml \
  --set secrets.POSTGRES_PASSWORD="..." \
  --set secrets.JWT_SECRET="..."
```

### Using External Database

To use a managed PostgreSQL (RDS, Cloud SQL, etc.):

```bash
helm upgrade --install finmind deploy/helm/finmind \
  --set postgresql.enabled=false \
  --set secrets.POSTGRES_PASSWORD="..." \
  --set secrets.JWT_SECRET="..." \
  # Override DATABASE_URL in backend config
```

**Files:**
- `deploy/helm/finmind/Chart.yaml`
- `deploy/helm/finmind/values.yaml`
- `deploy/helm/finmind/templates/` — All K8s resource templates

---

## Tilt (Local K8s Dev)

Tilt provides a fast inner-loop development experience on local Kubernetes with hot-reload.

### Prerequisites
- Docker Desktop with Kubernetes, minikube, kind, or k3d
- [Tilt](https://docs.tilt.dev/install.html) installed

### Run

```bash
cd deploy/tilt
tilt up
```

Open http://localhost:10350 to see the Tilt dashboard.

### Services in Tilt

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 5173 | Vite dev server with HMR |
| Backend | 8000 | Flask with live-reload |
| PostgreSQL | 5432 | Local database |
| Redis | 6379 | Cache |

### How Live Reload Works

- **Backend**: Python files are synced into the container. Gunicorn receives SIGHUP to reload.
- **Frontend**: Source files sync into the container. Vite HMR handles the rest instantly.
- **Dependencies**: If `requirements.txt` or `package.json` changes, a full image rebuild is triggered.

**Files:**
- `deploy/tilt/Tiltfile`

---

## Railway

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login and init
railway login
railway init

# 3. Add PostgreSQL and Redis plugins in the Railway dashboard
#    (Railway auto-sets DATABASE_URL and REDIS_URL)

# 4. Set secrets
railway variables set JWT_SECRET="$(openssl rand -hex 32)"

# 5. Deploy
railway up
```

**Files:** `deploy/platforms/railway/railway.toml`, `deploy/platforms/railway/railway.json`

---

## Render

Render uses a Blueprint file for one-click infrastructure setup.

```bash
# 1. Push repo to GitHub
# 2. Go to https://dashboard.render.com/blueprints
# 3. Click "New Blueprint Instance"
# 4. Connect your repo — Render auto-detects render.yaml
# 5. Set JWT_SECRET and API keys in the dashboard
```

Render automatically provisions PostgreSQL, Redis, TLS, and a `.onrender.com` domain.

**Files:** `deploy/platforms/render/render.yaml`

---

## Fly.io

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login
fly auth login

# 3. Create backend app
fly apps create finmind-backend

# 4. Provision database and cache
fly postgres create --name finmind-db
fly postgres attach finmind-db --app finmind-backend
fly redis create --name finmind-redis

# 5. Set secrets
fly secrets set JWT_SECRET="$(openssl rand -hex 32)" --app finmind-backend
fly secrets set REDIS_URL="<redis-url>" --app finmind-backend

# 6. Deploy backend
fly deploy --config deploy/platforms/fly/fly.toml

# 7. Deploy frontend
fly apps create finmind-frontend
fly deploy --config deploy/platforms/fly/fly-frontend.toml
```

**Files:** `deploy/platforms/fly/fly.toml`, `deploy/platforms/fly/fly-frontend.toml`

---

## Heroku

```bash
# 1. Install Heroku CLI
# 2. Login
heroku login

# 3. Create app with addons
heroku create finmind-backend
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# 4. Set config
heroku config:set JWT_SECRET="$(openssl rand -hex 32)"
heroku config:set LOG_LEVEL=INFO
heroku config:set GEMINI_MODEL=gemini-1.5-flash

# 5. Deploy via container
heroku container:push web --app finmind-backend \
  --dockerfile deploy/docker/backend.Dockerfile
heroku container:release web --app finmind-backend
```

**Files:** `deploy/platforms/heroku/Procfile`

---

## DigitalOcean

### App Platform

```bash
# 1. Install doctl
# 2. Deploy
doctl apps create --spec deploy/platforms/digitalocean/.do/app.yaml

# 3. Set secrets in the DigitalOcean dashboard
```

### Droplet

Use the unified deploy script for manual Droplet setup:

```bash
./deploy/scripts/deploy.sh --platform docker --env .env
```

**Files:** `deploy/platforms/digitalocean/.do/app.yaml`

---

## AWS

### ECS Fargate

```bash
# 1. Create ECR repository
aws ecr create-repository --repository-name finmind-backend

# 2. Build and push
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com
docker build -f deploy/docker/backend.Dockerfile -t finmind-backend .
docker tag finmind-backend:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

# 3. Create RDS PostgreSQL and ElastiCache Redis
# 4. Store secrets in AWS Secrets Manager
# 5. Register task definition
aws ecs register-task-definition --cli-input-json file://deploy/platforms/aws/ecs-task-definition.json

# 6. Create service
aws ecs create-service --cluster finmind --service-name finmind-backend \
  --task-definition finmind-backend --desired-count 2 --launch-type FARGATE
```

### App Runner

```bash
aws apprunner create-service --cli-input-yaml file://deploy/platforms/aws/apprunner.yaml
```

**Files:** `deploy/platforms/aws/ecs-task-definition.json`, `deploy/platforms/aws/apprunner.yaml`

---

## GCP Cloud Run

```bash
# 1. Set project
gcloud config set project YOUR_PROJECT_ID

# 2. Enable APIs
gcloud services enable run.googleapis.com sqladmin.googleapis.com redis.googleapis.com

# 3. Build and deploy
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/finmind-backend .
gcloud run deploy finmind-backend \
  --image gcr.io/YOUR_PROJECT_ID/finmind-backend \
  --region us-central1 --port 8000 \
  --min-instances 1 --max-instances 10 \
  --memory 512Mi --cpu 1

# 4. Create Cloud SQL PostgreSQL and Memorystore Redis
# 5. Store secrets in Secret Manager
# 6. Update service with secret bindings (see app.yaml)
```

**Files:** `deploy/platforms/gcp/app.yaml`

---

## Azure Container Apps

```bash
# 1. Create resource group and environment
az group create --name finmind-rg --location eastus
az containerapp env create --name finmind-env --resource-group finmind-rg

# 2. Create database and cache
az postgres flexible-server create --name finmind-db --resource-group finmind-rg
az redis create --name finmind-redis --resource-group finmind-rg --sku Basic --vm-size C0

# 3. Build and push to ACR
az acr create --name finmindacr --resource-group finmind-rg --sku Basic
az acr build --registry finmindacr --image finmind-backend:latest -f deploy/docker/backend.Dockerfile .

# 4. Deploy
az containerapp create --yaml deploy/platforms/azure/containerapp.yaml
```

**Files:** `deploy/platforms/azure/containerapp.yaml`

---

## Netlify (Frontend)

Netlify deploys only the React SPA frontend. The backend must be hosted separately.

```bash
# 1. Install Netlify CLI
npm i -g netlify-cli

# 2. Set VITE_API_URL in Netlify dashboard to your backend URL
# 3. Deploy
cd app
npm ci && npm run build
netlify deploy --prod --dir=dist
```

**Files:** `deploy/platforms/netlify/netlify.toml`

---

## Vercel (Frontend)

Vercel deploys only the React SPA frontend.

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Set VITE_API_URL in Vercel dashboard
# 3. Deploy
cd app
vercel --prod
```

**Files:** `deploy/platforms/vercel/vercel.json`

---

## Troubleshooting

### Backend won't start: "database not initialized"

The backend runs `flask init-db` on startup. If PostgreSQL is not ready yet, this will fail. Ensure:
- PostgreSQL health check passes before backend starts
- `DATABASE_URL` is correctly formatted
- Database user has permissions to create tables

```bash
# Check PostgreSQL is ready
docker compose exec postgres pg_isready -U finmind

# Manually initialize
docker compose exec backend python -m flask --app wsgi:app init-db
```

### Frontend shows blank page

The React SPA needs `VITE_API_URL` set at **build time** (it is baked into the JS bundle):

```bash
# Rebuild frontend with correct API URL
docker compose build --build-arg VITE_API_URL=https://api.yourdomain.com frontend
```

### Health check fails on port 8080

Some platforms (Fly.io, Cloud Run) expect port 8080. Set `GUNICORN_BIND=0.0.0.0:8080` in your environment.

### Redis connection refused

Verify the `REDIS_URL` environment variable points to the correct host:
- Docker Compose: `redis://redis:6379/0`
- Kubernetes: `redis://finmind-redis:6379/0` (service name)
- Managed Redis: use the connection string provided by your cloud provider

### Kubernetes pods in CrashLoopBackOff

```bash
# Check pod logs
kubectl logs -n finmind <pod-name> --previous

# Check events
kubectl describe pod -n finmind <pod-name>

# Common causes:
# - Secret not created (POSTGRES_PASSWORD, JWT_SECRET are required)
# - Database not reachable
# - Image pull failures
```

### TLS/HTTPS not working on Kubernetes

Ensure:
1. cert-manager is installed: `kubectl get pods -n cert-manager`
2. A ClusterIssuer exists: `kubectl get clusterissuer letsencrypt-prod`
3. DNS points to the ingress controller's external IP
4. The ingress annotation `cert-manager.io/cluster-issuer` matches your issuer name

### "Permission denied" on deploy scripts

```bash
chmod +x deploy/scripts/deploy.sh deploy/scripts/setup-local.sh
```
