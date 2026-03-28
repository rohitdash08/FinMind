# FinMind Deployment Guide

Production-grade, one-click deployments for every major platform.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/rohitdash08/FinMind && cd FinMind

# Deploy locally with Docker Compose (no setup required)
./scripts/deploy.sh docker

# Deploy to any cloud in one command
./scripts/deploy.sh [platform]
```

### All supported platforms

| Platform | Command | Type |
|---|---|---|
| Docker Compose | `./scripts/deploy.sh docker` | Local |
| Kubernetes (raw) | `./scripts/deploy.sh k8s` | K8s |
| Kubernetes (Helm) | `./scripts/deploy.sh helm` | K8s |
| Tilt (local K8s dev) | `./scripts/deploy.sh tilt` | Local K8s |
| Railway | `./scripts/deploy.sh railway` | PaaS |
| Render | `./scripts/deploy.sh render` | PaaS |
| Fly.io | `./scripts/deploy.sh fly` | PaaS |
| Heroku | `./scripts/deploy.sh heroku` | PaaS |
| DigitalOcean App Platform | `./scripts/deploy.sh digitalocean` | PaaS |
| AWS ECS/Fargate | `./scripts/deploy.sh aws` | Cloud |
| Google Cloud Run | `./scripts/deploy.sh gcp` | Cloud |
| Azure Container Apps | `./scripts/deploy.sh azure` | Cloud |
| Netlify (frontend) | `./scripts/deploy.sh netlify` | Static |
| Vercel (frontend) | `./scripts/deploy.sh vercel` | Static |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      Internet                        │
└────────────────────────┬────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    Nginx (proxy)    │ :8080
              └──────┬──────┬───────┘
                     │      │
        ┌────────────▼──┐ ┌─▼──────────────┐
        │  Backend API  │ │    Frontend     │
        │ Flask/Gunicorn│ │  React (Nginx)  │
        │    :8000      │ │     :80         │
        └───────┬───────┘ └────────────────┘
                │
     ┌──────────┼──────────┐
     │          │          │
┌────▼───┐ ┌───▼───┐ ┌────▼────┐
│Postgres│ │ Redis │ │Prometheus│
│  :5432 │ │ :6379 │ │  :9090  │
└────────┘ └───────┘ └────┬────┘
                           │
                    ┌──────▼──────┐
                    │   Grafana   │
                    │    :3000    │
                    └─────────────┘
```

---

## 1. Docker Compose

**Prerequisites:** Docker ≥ 24, Docker Compose ≥ 2.20

### Setup (3 steps)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, JWT_SECRET, GEMINI_API_KEY

# 2. Start the full stack
./scripts/deploy.sh docker
# or: docker compose up -d

# 3. Verify
curl http://localhost:8080/health
```

**Access:**
- API:      http://localhost:8080
- Frontend: http://localhost:5173
- Grafana:  http://localhost:3000 (admin / change-me-admin-password)

**Useful commands:**
```bash
docker compose logs -f backend        # stream backend logs
docker compose exec backend flask shell  # open Flask shell
docker compose down -v                # stop and remove volumes
```

---

## 2. Kubernetes — Raw Manifests

**Prerequisites:** kubectl, a running K8s cluster (minikube, kind, GKE, EKS, AKS…)

### Setup (3 steps)

```bash
# 1. Copy and edit secrets
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml — base64-encode all values:
#   echo -n "mypassword" | base64

# 2. Apply all manifests
./scripts/deploy.sh k8s
# or manually:
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml -n finmind
kubectl apply -f deploy/k8s/app-stack.yaml -n finmind
kubectl apply -f deploy/k8s/monitoring-stack.yaml -n finmind

# 3. Verify
kubectl get pods -n finmind
kubectl rollout status deployment/backend -n finmind
```

**Port-forward for local access:**
```bash
kubectl port-forward svc/nginx 8080:8080 -n finmind &
kubectl port-forward svc/grafana 3000:3000 -n finmind &
```

---

## 3. Kubernetes — Helm

**Prerequisites:** helm ≥ 3.12, kubectl

### Setup (3 steps)

```bash
# 1. Create namespace and install
kubectl create namespace finmind --dry-run=client -o yaml | kubectl apply -f -

# 2. Install with your values
helm upgrade --install finmind deploy/k8s/helm \
  --namespace finmind \
  --set secrets.postgresPassword=$(echo -n "yourpassword" | base64) \
  --set secrets.jwtSecret=$(openssl rand -base64 32 | base64) \
  --set ingress.hosts.api=api.yourdomain.com \
  --set ingress.hosts.app=app.yourdomain.com \
  --wait

# 3. Verify
helm status finmind -n finmind
kubectl get pods -n finmind
```

**Custom values file (recommended for production):**
```yaml
# my-prod-values.yaml
ingress:
  hosts:
    api: api.yourdomain.com
    app: app.yourdomain.com
    grafana: grafana.yourdomain.com
  tls:
    enabled: true
secrets:
  postgresPassword: <base64>
  jwtSecret: <base64>
  geminiApiKey: <base64>
backend:
  replicaCount: 3
  autoscaling:
    enabled: true
    maxReplicas: 10
```

```bash
helm upgrade --install finmind deploy/k8s/helm \
  -f my-prod-values.yaml --namespace finmind --wait
```

**Helm chart structure:**
```
deploy/k8s/helm/
├── Chart.yaml          # Chart metadata
├── values.yaml         # Default values (fully documented)
└── templates/
    ├── configmap.yaml  # App config + Nginx config
    ├── secrets.yaml    # K8s Secret (all credentials)
    ├── pvc.yaml        # PersistentVolumeClaims
    ├── deployment.yaml # All Deployments (postgres, redis, backend, frontend, nginx)
    ├── service.yaml    # ClusterIP Services
    ├── ingress.yaml    # Ingress with TLS (cert-manager annotations)
    └── hpa.yaml        # HorizontalPodAutoscalers (backend + frontend)
```

---

## 4. Tilt — Local K8s Dev with Hot-Reload

**Prerequisites:** tilt ≥ 0.33, kubectl, helm, Docker

### Setup (3 steps)

```bash
# 1. Start a local cluster (if needed)
minikube start   # or: kind create cluster

# 2. Launch Tilt
./scripts/deploy.sh tilt
# or: cd deploy/tilt && tilt up

# 3. Open the Tilt UI
open http://localhost:10350
```

**Features:**
- Live sync: Python/React source files sync into running containers without rebuild
- Auto-test: backend tests and frontend lint triggered on file change (manual trigger in UI)
- Port-forwards: backend :8000, frontend :5173, Grafana :3000, Prometheus :9090

---

## 5. Railway

**Prerequisites:** Railway CLI (`npm i -g @railway/cli`), Railway account

### Setup (3 steps)

```bash
# 1. Login and link project
railway login
railway init   # or: railway link <project-id>

# 2. Add secrets
railway variables set JWT_SECRET=$(openssl rand -hex 32)
railway variables set GEMINI_API_KEY=your-key

# 3. Deploy
./scripts/deploy.sh railway
```

Railway auto-provisions PostgreSQL and Redis plugins. The `DATABASE_URL` and `REDIS_URL` are injected automatically.

---

## 6. Render

**Prerequisites:** Render account, GitHub repo connected

### Setup (3 steps)

```bash
# 1. One-click deploy via Blueprint
# Go to: https://render.com/deploy
# Paste your GitHub repo URL — Render reads deploy/platforms/render/render.yaml

# 2. Set secrets in Render dashboard:
#   JWT_SECRET, GEMINI_API_KEY

# 3. Trigger deploy
git push origin main   # auto-deploys on push
```

The Blueprint provisions: backend web service, frontend static site, PostgreSQL, Redis.

---

## 7. Fly.io

**Prerequisites:** `flyctl` CLI, Fly account

### Setup (3 steps)

```bash
# 1. Login and create app
flyctl auth login
flyctl apps create finmind-backend --org personal

# 2. Set secrets
flyctl secrets set \
  DATABASE_URL="postgresql://..." \
  REDIS_URL="redis://..." \
  JWT_SECRET="$(openssl rand -hex 32)" \
  GEMINI_API_KEY="your-key"

# 3. Deploy
./scripts/deploy.sh fly
# or: flyctl deploy --config deploy/platforms/fly/fly.toml
```

**Scale:**
```bash
flyctl scale count 3      # run 3 machines
flyctl scale vm shared-cpu-2x  # upgrade machine size
```

---

## 8. Heroku

**Prerequisites:** Heroku CLI, Heroku account, git remote configured

### Setup (3 steps)

```bash
# 1. Create app and add-ons
heroku create finmind
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# 2. Set config vars
heroku config:set \
  JWT_SECRET=$(openssl rand -hex 32) \
  GEMINI_API_KEY=your-key \
  LOG_LEVEL=INFO

# 3. Deploy
./scripts/deploy.sh heroku
# or: git push heroku main
```

The `Procfile` runs `flask init-db` as a release phase command automatically.

---

## 9. DigitalOcean App Platform

**Prerequisites:** `doctl` CLI, DigitalOcean account

### Setup (3 steps)

```bash
# 1. Authenticate
doctl auth init

# 2. Set secrets in the spec or via dashboard:
#   JWT_SECRET, GEMINI_API_KEY

# 3. Deploy
./scripts/deploy.sh digitalocean
# or: doctl apps create --spec deploy/platforms/digitalocean/app.yaml
```

The app spec provisions: backend service, frontend static site, managed PostgreSQL 16, managed Redis 7.

---

## 10. AWS ECS / Fargate

**Prerequisites:** AWS CLI v2, configured credentials (`aws configure`), existing ECS cluster

### Setup (3 steps)

```bash
# 1. Create secrets in AWS Secrets Manager
aws secretsmanager create-secret --name finmind/DATABASE_URL --secret-string "postgresql://..."
aws secretsmanager create-secret --name finmind/REDIS_URL    --secret-string "redis://..."
aws secretsmanager create-secret --name finmind/JWT_SECRET   --secret-string "$(openssl rand -hex 32)"
aws secretsmanager create-secret --name finmind/GEMINI_API_KEY --secret-string "your-key"

# 2. Edit task definition — replace ACCOUNT_ID and REGION placeholders
sed -i 's/ACCOUNT_ID/123456789012/g; s/REGION/us-east-1/g' \
  deploy/platforms/aws/task-definition.json

# 3. Register and deploy
export AWS_ECS_CLUSTER=finmind AWS_ECS_SERVICE=finmind-backend AWS_REGION=us-east-1
./scripts/deploy.sh aws
```

---

## 11. Google Cloud Run

**Prerequisites:** `gcloud` CLI, GCP project with billing enabled

### Setup (3 steps)

```bash
# 1. Authenticate and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. Store secrets in Secret Manager
gcloud secrets create finmind-database-url --data-file=- <<< "postgresql://..."
gcloud secrets create finmind-redis-url    --data-file=- <<< "redis://..."
gcloud secrets create finmind-jwt-secret   --data-file=- <<< "$(openssl rand -hex 32)"
gcloud secrets create finmind-gemini-api-key --data-file=- <<< "your-key"

# Grant Cloud Run SA access to secrets
gcloud secrets add-iam-policy-binding finmind-jwt-secret \
  --member="serviceAccount:finmind-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 3. Deploy
export GCP_PROJECT_ID=YOUR_PROJECT_ID GCP_REGION=us-east1
./scripts/deploy.sh gcp
```

---

## 12. Azure Container Apps

**Prerequisites:** Azure CLI (`az`), Azure subscription

### Setup (3 steps)

```bash
# 1. Login and create resource group
az login
az group create -n finmind-rg --location eastus
az containerapp env create -n finmind-env -g finmind-rg --location eastus

# 2. Store secrets in Key Vault
az keyvault create -n finmind-kv -g finmind-rg --location eastus
az keyvault secret set --vault-name finmind-kv -n DATABASE-URL --value "postgresql://..."
az keyvault secret set --vault-name finmind-kv -n REDIS-URL    --value "redis://..."
az keyvault secret set --vault-name finmind-kv -n JWT-SECRET   --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name finmind-kv -n GEMINI-API-KEY --value "your-key"

# 3. Deploy
export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
./scripts/deploy.sh azure
```

---

## 13. Netlify (Frontend)

**Prerequisites:** Netlify CLI (`npm i -g netlify-cli`), Netlify account

### Setup (3 steps)

```bash
# 1. Login
netlify login

# 2. Set backend URL env var in Netlify dashboard:
#   VITE_API_URL = https://your-backend-url

# 3. Deploy
./scripts/deploy.sh netlify
# or: cd app && netlify deploy --prod
```

The `netlify.toml` configures SPA routing, API proxy, security headers, and asset caching.

---

## 14. Vercel (Frontend)

**Prerequisites:** Vercel CLI (`npm i -g vercel`), Vercel account

### Setup (3 steps)

```bash
# 1. Login
vercel login

# 2. Set secret in Vercel dashboard or CLI:
vercel env add VITE_API_URL production   # enter your backend URL

# 3. Deploy
./scripts/deploy.sh vercel
# or: cd app && vercel --prod
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `JWT_SECRET` | Yes | — | Secret for signing JWT tokens (≥32 chars) |
| `GEMINI_API_KEY` | No | — | Google Gemini API key for AI features |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `PORT` | No | `8000` | Backend HTTP port (set by platform) |
| `PROMETHEUS_MULTIPROC_DIR` | No | `/tmp/prometheus_multiproc` | Prometheus multiprocess dir |

---

## Monitoring

All deployments include Prometheus + Grafana + Loki (where supported).

| Service | URL | Default Credentials |
|---|---|---|
| Grafana | http://localhost:3000 (Docker) | admin / change-me-admin-password |
| Prometheus | http://localhost:9090 (Docker) | — |
| Backend metrics | http://localhost:8000/metrics | — |

**Scraped targets:**
- Backend application (`/metrics`)
- PostgreSQL (`postgres-exporter`)
- Redis (`redis-exporter`)
- Nginx (`nginx-exporter`)
- Node metrics (`node-exporter`)

---

## Secrets Generation

```bash
# Generate strong secrets for production
JWT_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/')

# Base64-encode for Kubernetes secrets
echo -n "$JWT_SECRET" | base64
echo -n "$POSTGRES_PASSWORD" | base64
```

---

## Troubleshooting

**Backend not starting:**
```bash
docker compose logs backend          # Docker
kubectl logs -l app=backend -n finmind  # K8s
```

**Database migration failed:**
```bash
docker compose exec backend flask init-db
kubectl exec -it deploy/backend -n finmind -- flask init-db
```

**Health check failing:**
```bash
curl http://localhost:8080/health     # should return {"status": "ok"}
```

**Helm dry-run:**
```bash
helm upgrade --install finmind deploy/k8s/helm --dry-run --debug -n finmind
```

**Deploy script dry-run:**
```bash
./scripts/deploy.sh helm --dry-run
```
