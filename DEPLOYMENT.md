# FinMind Universal Deployment Guide

Production-ready, one-click deployment support for FinMind across all major platforms.

## 🚀 One-Command Deployment

```bash
# Docker Compose (local development)
./scripts/deploy.sh docker

# Docker Compose (production)
./scripts/deploy.sh docker-prod

# Kubernetes (Helm)
./scripts/deploy.sh helm

# Local K8s with Tilt
./scripts/deploy.sh tilt

# Fly.io
./scripts/deploy.sh fly

# Railway
./scripts/deploy.sh railway
```

**Windows PowerShell:**
```powershell
.\scripts\deploy.ps1 docker
.\scripts\deploy.ps1 helm
```

---

## 🎯 Quick Deploy Buttons

### Full-Stack Platforms

| Platform | Deploy Button | Free Tier | Notes |
|----------|---------------|-----------|-------|
| Railway | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/finmind) | ✅ $5/mo credit | Best for startups |
| Render | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind) | ✅ Limited | Auto-scaling |
| Heroku | [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind) | ❌ | Enterprise ready |
| DigitalOcean | [![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main) | ❌ | Simple pricing |

### Frontend Only

| Platform | Deploy Button | Best For |
|----------|---------------|----------|
| Vercel | [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app) | React/Next.js |
| Netlify | [![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind) | JAMstack |

---

## 📦 Deployment Options

### 1. Docker Compose (Recommended for Local/VPS)

**Development (with hot-reload):**
```bash
cp .env.example .env
# Edit .env with your secrets
docker compose up --build
```

**Production (optimized):**
```bash
cp .env.example .env.production
# Edit .env.production with production secrets
docker compose -f docker-compose.prod.yml up -d
```

**Services:**
| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:5173 | Vite dev server |
| Backend | http://localhost:8000 | Flask API |
| Nginx | http://localhost:8080 | Reverse proxy |
| Grafana | http://localhost:3000 | Monitoring |
| Prometheus | http://localhost:9090 | Metrics |

### 2. Kubernetes (Production Scale)

**With Helm (recommended):**
```bash
cd deploy/helm/finmind
helm repo add bitnami https://charts.bitnami.com/bitnami
helm dependency update

helm install finmind . \
  --namespace finmind --create-namespace \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgresql.auth.password=$(openssl rand -base64 16) \
  --set ingress.hosts[0].host=api.yourdomain.com
```

**With raw manifests:**
```bash
kubectl apply -f deploy/k8s/namespace.yaml
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
```

**Features included:**
- ✅ Horizontal Pod Autoscaler (HPA)
- ✅ Pod Disruption Budget (PDB)
- ✅ Ingress with TLS (cert-manager ready)
- ✅ Prometheus metrics & ServiceMonitor
- ✅ Network Policies (optional)
- ✅ Health probes (liveness/readiness)

### 3. Local K8s Development (Tilt)

Perfect for developing with Kubernetes locally:

```bash
# Prerequisites: Docker Desktop/Rancher with K8s, Tilt installed
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml

tilt up
```

**Tilt provides:**
- Live code sync (no rebuilds needed)
- Unified log viewer
- One-click test runners
- Production-parity K8s environment

See [deploy/tilt/README.md](deploy/tilt/README.md) for details.

---

## ☁️ Cloud Platform Guides

### Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
flyctl launch --config deploy/fly/fly.toml
flyctl secrets set JWT_SECRET=$(openssl rand -hex 32)
flyctl secrets set DATABASE_URL="postgres://..."
flyctl secrets set REDIS_URL="redis://..."
flyctl deploy
```

### Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway link
railway up
```

Or use the Deploy button above.

### Render

Deploy with [render.yaml](deploy/render/render.yaml) blueprint:
1. Connect your GitHub repo
2. Render auto-detects the blueprint
3. Click Deploy

### AWS (ECS Fargate / App Runner)

**App Runner (simplest):**
```bash
# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker build -t finmind-backend ./packages/backend
docker tag finmind-backend:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/finmind-backend:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/finmind-backend:latest

# Deploy with CloudFormation
aws cloudformation deploy \
  --template-file deploy/aws/apprunner.yaml \
  --stack-name finmind \
  --parameter-overrides \
    ImageUri=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/finmind-backend:latest \
    DatabaseUrl="postgresql://..." \
    RedisUrl="redis://..."
```

**ECS Fargate:** See [deploy/aws/README.md](deploy/aws/README.md)

### GCP Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/$PROJECT/finmind-backend ./packages/backend

# Deploy
gcloud run deploy finmind-backend \
  --image gcr.io/$PROJECT/finmind-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=...,REDIS_URL=...,JWT_SECRET=..."
```

### Azure Container Apps

```bash
# Create environment
az containerapp env create --name finmind-env --resource-group finmind-rg

# Deploy
az containerapp create \
  --name finmind-backend \
  --resource-group finmind-rg \
  --environment finmind-env \
  --image ghcr.io/rohitdash08/finmind-backend:latest \
  --target-port 8000 \
  --env-vars "DATABASE_URL=..." "REDIS_URL=..." "JWT_SECRET=..." \
  --ingress external
```

### DigitalOcean Droplet (VPS)

One-command setup on Ubuntu:
```bash
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/droplet/setup.sh | sudo bash
```

This installs Docker, clones the repo, sets up Nginx with SSL, and starts the app.

---

## 🔧 Environment Variables

### Required

| Variable | Description | Generate |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection | Platform-provided |
| `REDIS_URL` | Redis connection | Platform-provided |
| `JWT_SECRET` | JWT signing secret | `openssl rand -hex 32` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API | - |
| `OPENAI_API_KEY` | OpenAI API (alternative) | - |
| `LOG_LEVEL` | Logging level | `INFO` |
| `GEMINI_MODEL` | Gemini model | `gemini-1.5-flash` |
| `TWILIO_ACCOUNT_SID` | Twilio for WhatsApp | - |
| `TWILIO_AUTH_TOKEN` | Twilio auth | - |
| `SMTP_URL` | Email SMTP | - |

### Frontend

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API URL |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   CDN/Edge      │
│   (React/Vite)  │     │ (Vercel/Netlify)│
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
┌─────────────────┐     ┌─────────────────┐
│   Load Balancer │────▶│   Backend API   │
│   (Nginx/ALB)   │     │   (Flask)       │
└─────────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
           ┌─────────────────┐       ┌─────────────────┐
           │   PostgreSQL    │       │     Redis       │
           │   (Database)    │       │    (Cache)      │
           └─────────────────┘       └─────────────────┘
```

---

## 📊 CI/CD Pipelines

### Automatic Docker Builds

On push to `main`, images are built and pushed to GHCR:
- `ghcr.io/<owner>/finmind-backend:latest`
- `ghcr.io/<owner>/finmind-frontend:latest`

### Continuous Deployment

Trigger deployments via GitHub Actions:
```yaml
# .github/workflows/cd.yml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      deploy_to: [fly, railway, kubernetes]
```

### GitOps (Kubernetes)

On release, image tags are automatically updated in `deploy/k8s/app-stack.yaml` for ArgoCD/Flux to pick up.

---

## 🔒 Security Checklist

- [ ] Generate strong JWT secret: `openssl rand -hex 32`
- [ ] Use strong database passwords
- [ ] Enable HTTPS/TLS everywhere
- [ ] Configure CORS properly
- [ ] Enable rate limiting
- [ ] Set security headers (CSP, HSTS, etc.)
- [ ] Regular security updates
- [ ] Enable network policies (K8s)
- [ ] Use secrets management (not env vars in plain text)

---

## 📈 Monitoring & Observability

All deployments include Prometheus metrics at `/metrics`:
- Request count by endpoint/status
- Request duration histograms (p50, p95, p99)
- Reminder event counters
- Database/Redis connection stats

### Full Observability Stack (Docker Compose)

```bash
docker compose up
```

Includes:
- **Grafana** (http://localhost:3000) - Dashboards
- **Prometheus** (http://localhost:9090) - Metrics
- **Loki** (http://localhost:3100) - Logs

### Kubernetes ServiceMonitor

Enable in Helm values:
```yaml
metrics:
  serviceMonitor:
    enabled: true
```

---

## 🆘 Troubleshooting

### Health Check Failing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Check logs
docker compose logs backend
kubectl logs -n finmind -l app=backend
```

### Database Connection Issues

```bash
# Verify DATABASE_URL format
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE

# Test connection
docker compose exec backend python -c "from app import db; print(db.engine.url)"
```

### Pod Not Starting (K8s)

```bash
kubectl describe pod -n finmind <pod-name>
kubectl get events -n finmind --sort-by='.lastTimestamp'
```

---

## 📚 Platform-Specific Documentation

| Platform | Guide |
|----------|-------|
| Railway | [deploy/railway/README.md](deploy/railway/README.md) |
| Render | [deploy/render/README.md](deploy/render/README.md) |
| Fly.io | [deploy/fly/README.md](deploy/fly/README.md) |
| Heroku | [deploy/heroku/README.md](deploy/heroku/README.md) |
| AWS | [deploy/aws/README.md](deploy/aws/README.md) |
| GCP | [deploy/gcp/README.md](deploy/gcp/README.md) |
| Azure | [deploy/azure/README.md](deploy/azure/README.md) |
| DigitalOcean | [deploy/digitalocean/README.md](deploy/digitalocean/README.md) |
| Kubernetes/Helm | [deploy/helm/README.md](deploy/helm/README.md) |
| Tilt | [deploy/tilt/README.md](deploy/tilt/README.md) |

---

## 💰 Cost Estimates

| Setup | Monthly Cost | Best For |
|-------|--------------|----------|
| Free Tier (Railway/Render) | $0-5 | Hobby/Testing |
| VPS (DigitalOcean Droplet) | $12-24 | Small production |
| PaaS (Render/Fly.io paid) | $25-50 | Startups |
| K8s (DigitalOcean/Linode) | $50-100 | Scale |
| AWS/GCP/Azure | $100+ | Enterprise |

---

## 📝 License

MIT License - See [LICENSE](LICENSE)
