# FinMind Deployment Guide

One-click and one-command deployment paths for FinMind across Docker, Kubernetes, and major cloud platforms.

## Quick Start (Docker Compose)

```bash
git clone https://github.com/rohitdash08/FinMind.git && cd FinMind
cp .env.example .env          # edit secrets before production use
docker compose up -d           # dev stack with monitoring
# or
docker compose -f docker-compose.prod.yml up -d   # production (no dev tools)
```

Endpoints after startup:
| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| Frontend | http://localhost:5173 (dev) / http://localhost:80 (prod) |
| Health check | http://localhost:8000/health |
| Metrics | http://localhost:8000/metrics |
| Grafana | http://localhost:3000 (dev stack only) |

---

## Deploy Buttons

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/finmind?referralCode=finmind)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main)

---

## Platform-Specific Guides

### Railway
```bash
# Install Railway CLI, then:
railway login
railway init
railway up
```
Config: [`deploy/platforms/railway.toml`](deploy/platforms/railway.toml)

### Render
Import from GitHub and Render auto-detects the blueprint.
Config: [`deploy/platforms/render.yaml`](deploy/platforms/render.yaml)

### Fly.io
```bash
fly auth login
fly launch --config deploy/platforms/fly.toml
fly secrets set DATABASE_URL="..." JWT_SECRET="..." REDIS_URL="..."
fly deploy
```
Config: [`deploy/platforms/fly.toml`](deploy/platforms/fly.toml)

### Heroku
```bash
heroku create finmind-app
heroku stack:set container
git push heroku main
```
Config: [`deploy/platforms/heroku.yml`](deploy/platforms/heroku.yml)

### DigitalOcean App Platform
```bash
doctl apps create --spec deploy/platforms/digitalocean-app.yaml
```
Config: [`deploy/platforms/digitalocean-app.yaml`](deploy/platforms/digitalocean-app.yaml)

### DigitalOcean Droplet
```bash
ssh root@your-droplet 'bash -s' < deploy/platforms/digitalocean-droplet.sh
```

### AWS ECS Fargate
```bash
# Push image to ECR or use GHCR, then:
aws ecs register-task-definition --cli-input-json file://deploy/platforms/aws-ecs-task-definition.json
aws ecs create-service --cluster finmind --task-definition finmind-backend --desired-count 2 --launch-type FARGATE
```
Config: [`deploy/platforms/aws-ecs-task-definition.json`](deploy/platforms/aws-ecs-task-definition.json)

### GCP Cloud Run
```bash
gcloud builds submit --tag gcr.io/$PROJECT_ID/finmind-backend ./packages/backend
gcloud run deploy finmind-backend --image gcr.io/$PROJECT_ID/finmind-backend --port 8000 --allow-unauthenticated
```
Config: [`deploy/platforms/gcp-cloudrun.yaml`](deploy/platforms/gcp-cloudrun.yaml)

### Azure Container Apps
```bash
az containerapp up --name finmind-backend \
  --resource-group finmind-rg \
  --source ./packages/backend \
  --ingress external --target-port 8000
```
Config: [`deploy/platforms/azure-container-app.yaml`](deploy/platforms/azure-container-app.yaml)

### Netlify (Frontend)
```bash
cd app && npm ci && npm run build
# Deploy dist/ to Netlify, or connect repo and set:
#   Build command: cd app && npm ci && npm run build
#   Publish directory: app/dist
```

### Vercel (Frontend)
```bash
cd app && vercel
# Or connect repo with:
#   Framework: Vite
#   Root directory: app
#   Build command: npm run build
#   Output directory: dist
```

---

## Kubernetes (Helm)

### Prerequisites
- kubectl configured for your cluster
- Helm 3.x installed
- (Optional) cert-manager for TLS, nginx-ingress for ingress

### Install
```bash
# Development
helm install finmind ./deploy/helm/finmind --namespace finmind --create-namespace

# Production with TLS + autoscaling
helm install finmind ./deploy/helm/finmind \
  --namespace finmind --create-namespace \
  -f deploy/helm/finmind/values.production.yaml \
  --set secrets.postgresPassword="$(openssl rand -hex 16)" \
  --set secrets.jwtSecret="$(openssl rand -hex 32)"

# Or use the helper script
./scripts/deploy-helm.sh finmind finmind deploy/helm/finmind/values.production.yaml
```

### Upgrade
```bash
helm upgrade finmind ./deploy/helm/finmind --namespace finmind
```

### Uninstall
```bash
helm uninstall finmind --namespace finmind
```

### Features
- HorizontalPodAutoscaler (2-10 replicas, CPU/memory based)
- Ingress with TLS via cert-manager
- Health probes (readiness + liveness) on all components
- Secret management via Kubernetes Secrets
- Configurable resource requests/limits

---

## Tilt (Local K8s Dev)

### Prerequisites
- [Tilt](https://tilt.dev/) installed
- Local K8s cluster (minikube, kind, k3d, or Docker Desktop)

### Start
```bash
tilt up
```
This will:
1. Build backend and frontend Docker images locally
2. Apply K8s manifests to your local cluster
3. Set up port-forwards (backend:8000, nginx:8080)
4. Start a local frontend dev server on :5173
5. Live-update code changes without full rebuilds

### Dashboard
Open http://localhost:10350 for the Tilt UI.

---

## CI/CD

The repo includes GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`): lint, test, security scan on every push/PR
- **Docker Publish** (`.github/workflows/docker-publish.yml`): build and push images to GHCR on main/tags

### Automated flow
1. Push to `main` or create a tag `v*`
2. CI runs tests + linting
3. Docker images are built and pushed to `ghcr.io`
4. Smoke test verifies the stack starts correctly

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+psycopg2://finmind:finmind@postgres:5432/finmind` | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET` | Yes | `dev-secret-change` | JWT signing key (change in production!) |
| `POSTGRES_USER` | Yes | `finmind` | PostgreSQL user |
| `POSTGRES_PASSWORD` | Yes | `finmind` | PostgreSQL password |
| `POSTGRES_DB` | Yes | `finmind` | PostgreSQL database name |
| `GEMINI_API_KEY` | No | `""` | Google Gemini API key for AI insights |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name |
| `OPENAI_API_KEY` | No | `""` | OpenAI API key (alternative to Gemini) |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `TWILIO_ACCOUNT_SID` | No | `""` | Twilio SID for WhatsApp reminders |
| `TWILIO_AUTH_TOKEN` | No | `""` | Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | No | `""` | Twilio WhatsApp sender number |
| `VITE_API_URL` | No | `http://localhost:8000` | Backend URL for frontend |

---

## Verification Checklist

After deploying on any platform, verify:

- [ ] Frontend loads at the configured URL
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `POST /auth/register` creates a user
- [ ] `POST /auth/login` returns JWT tokens
- [ ] Expenses CRUD works
- [ ] Bills CRUD works
- [ ] Dashboard data loads
- [ ] Redis caching is active (check response times)
