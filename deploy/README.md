# FinMind — Deployment Guide

> See also: [DEPLOY.md](../DEPLOY.md) in the project root for quick deploy buttons and overview.

FinMind supports deployment to 12+ platforms. Each platform has its own directory with configuration files, deploy scripts, and a README.

## Quick Start

```bash
# Local development
make dev                    # Docker Compose
make tilt                   # Tilt (local K8s)

# Production
make prod                   # Docker Compose (production mode)
make helm-install           # Kubernetes via Helm

# Validate deployment
./scripts/validate-deploy.sh http://your-backend-url
```

## Platform Matrix

| Platform | Type | Config | Script | README | Difficulty |
|----------|------|--------|--------|--------|------------|
| Docker Compose | Local | `docker-compose.yml` | `make dev` | — | 🟢 |
| Tilt | Local K8s | `Tiltfile` | `tilt up` | [README](tilt/README.md) | 🟢 |
| Railway | PaaS | [railway.toml](railway/railway.toml) | — | [README](railway/README.md) | 🟢 |
| Heroku | PaaS | [app.json](heroku/app.json) | — | [README](heroku/README.md) | 🟢 |
| Render | PaaS | [render.yaml](render/render.yaml) | — | [README](render/README.md) | 🟢 |
| Fly.io | PaaS | [fly.toml](fly/fly.toml) | [deploy.sh](fly/deploy.sh) | [README](fly/README.md) | 🟡 |
| DigitalOcean App | PaaS | [app.yaml](digitalocean/.do/app.yaml) | — | [README](digitalocean/README.md) | 🟢 |
| DigitalOcean Droplet | VPS | — | [setup.sh](digitalocean/scripts/droplet-setup.sh) | [README](digitalocean/README.md) | 🟡 |
| AWS ECS Fargate | Cloud | [cloudformation.yaml](aws/cloudformation.yaml) | [deploy.sh](aws/deploy.sh) | [README](aws/README.md) | 🔴 |
| AWS App Runner | Cloud | [apprunner.yaml](aws/apprunner.yaml) | — | [README](aws/README.md) | 🟡 |
| GCP Cloud Run | Cloud | [service.yaml](gcp/service.yaml) | [deploy.sh](gcp/deploy.sh) | [README](gcp/README.md) | 🟡 |
| Azure Container Apps | Cloud | [main.bicep](azure/bicep/main.bicep) | [deploy.sh](azure/deploy.sh) | [README](azure/README.md) | 🟡 |
| Helm (K8s) | K8s | [Chart.yaml](helm/finmind/Chart.yaml) | `helm install` | [README](helm/README.md) | 🔴 |
| Raw K8s | K8s | [app-stack.yaml](k8s/app-stack.yaml) | — | [README](k8s/README.md) | 🔴 |
| Netlify | Frontend | [netlify.toml](netlify/netlify.toml) | — | [README](netlify/README.md) | 🟢 |
| Vercel | Frontend | [vercel.json](vercel/vercel.json) | — | [README](vercel/README.md) | 🟢 |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL  │
│  React/Vite  │     │  Flask API   │     │     16       │
│  (Nginx)     │     │  (Gunicorn)  │     └─────────────┘
│  Port: 80    │     │  Port: 8000  │────▶┌─────────────┐
└─────────────┘     └─────────────┘     │    Redis 7   │
                                         └─────────────┘
```

## Monitoring Stack

Included in Docker Compose and Kubernetes deployments:

| Component | Purpose | Port |
|-----------|---------|------|
| Prometheus | Metrics collection | 9090 |
| Grafana | Dashboards | 3000 |
| Loki | Log aggregation | 3100 |
| Promtail | Log shipping | — |
| Node Exporter | Host metrics | 9100 |
| Postgres Exporter | DB metrics | 9187 |
| Redis Exporter | Cache metrics | 9121 |
| Nginx Exporter | Proxy metrics | 9113 |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `JWT_SECRET` | ✅ | JWT signing secret (≥32 chars) |
| `VITE_API_URL` | ✅* | Backend API URL (frontend build time) |
| `LOG_LEVEL` | ❌ | Log level (default: INFO) |
| `GEMINI_API_KEY` | ❌ | Google Gemini API key |
| `GEMINI_MODEL` | ❌ | Gemini model (default: gemini-1.5-flash) |
| `OPENAI_API_KEY` | ❌ | OpenAI API key |

## Validation

After deploying, run the validation script:

```bash
./scripts/validate-deploy.sh http://your-backend-url http://your-frontend-url
```

This checks:
- Frontend reachable
- Backend health endpoint
- Database + Redis connectivity
- Auth endpoints exist
- Core module endpoints (expenses, bills, reminders, dashboard, insights)

## Database Migration

All deployment methods automatically run `flask init-db` on startup. To run manually:

```bash
docker exec -it <backend-container> python -m flask --app wsgi:app init-db
```
