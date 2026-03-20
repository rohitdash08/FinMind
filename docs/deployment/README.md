# FinMind Deployment Guide

FinMind supports one-click deployment to multiple platforms. Choose the one that fits your needs.

## Quick Start

Run the interactive deploy script:

```bash
bash scripts/deploy.sh
```

## Architecture

- **Frontend**: Vite/React app built to static files, served by nginx on port 80
- **Backend**: Flask API served by gunicorn on port 8000
- **Database**: PostgreSQL 16
- **Cache**: Redis 7
- **Monitoring**: Prometheus + Grafana + Loki (optional)

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+psycopg2://...` or `postgres://...` — auto-converted) |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Secret for JWT token signing |
| `VITE_API_URL` | Backend URL (frontend build-time only) |

See `.env.example` for all variables.

---

## Platform Guides

### Docker Compose (Local/VPS)

```bash
cp .env.example .env
# Edit .env with your values
docker compose up -d
```

- Frontend: http://localhost:5173 (dev) or build with `app/Dockerfile`
- Backend: http://localhost:8000/health
- Grafana: http://localhost:3000

### Kubernetes

**Raw manifests:**
```bash
bash scripts/deploy-k8s.sh
```

**Helm chart** (recommended):
```bash
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind --create-namespace \
  --set secrets.jwtSecret="$(openssl rand -hex 32)" \
  --set secrets.postgresPassword="$(openssl rand -hex 16)"
```

Features: HPA, Ingress with TLS (cert-manager), ServiceMonitor, health probes.

See: [Kubernetes Guide](./kubernetes.md)

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?template=https://github.com/rohitdash08/FinMind)

1. Install [Railway CLI](https://docs.railway.app/develop/cli)
2. `railway login && railway init`
3. Add PostgreSQL and Redis plugins in the dashboard
4. Set env vars and deploy: `railway up`

See: [Railway Guide](./railway.md)

### Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

Or manually:
```bash
heroku create finmind-app
heroku stack:set container
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
git push heroku main
```

See: [Heroku Guide](./heroku.md)

### DigitalOcean

**App Platform:**
```bash
doctl apps create --spec .do/app.yaml
```

**Droplet:**
```bash
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/droplet/setup.sh | bash
```

See: [DigitalOcean Guide](./digitalocean.md)

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

1. Push to GitHub
2. Go to [Render Blueprints](https://dashboard.render.com/blueprints)
3. Connect repo — Render auto-detects `render.yaml`

See: [Render Guide](./render.md)

### Fly.io

```bash
bash deploy/fly/deploy.sh
```

See: [Fly.io Guide](./flyio.md)

### AWS

**ECS Fargate (CloudFormation):**
```bash
aws cloudformation deploy --template-file deploy/aws/cloudformation.yaml \
  --stack-name finmind --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides VpcId=<vpc> SubnetIds=<subnets> ...
```

**App Runner:** See `deploy/aws/apprunner.yaml`

See: [AWS Guide](./aws.md)

### GCP Cloud Run

```bash
gcloud builds submit --config deploy/gcp/cloudbuild.yaml
```

See: [GCP Guide](./gcp.md)

### Azure Container Apps

```bash
az deployment group create --resource-group finmind-rg \
  --template-file deploy/azure/main.bicep \
  --parameters backendImage=<img> frontendImage=<img> ...
```

See: [Azure Guide](./azure.md)

### Netlify (Frontend Only)

Connect GitHub repo at [Netlify](https://app.netlify.com). Auto-detects `netlify.toml`.
Set `VITE_API_URL` to your backend URL in site environment variables.

### Vercel (Frontend Only)

```bash
cd app && vercel --prod
```

Set `VITE_API_URL` environment variable in the Vercel dashboard.

---

## Verification Checklist

After deploying on any platform, verify:

- [ ] Frontend loads and is reachable
- [ ] `GET /health` returns 200 on the backend
- [ ] Database is connected (user registration works)
- [ ] Redis is connected (sessions/caching work)
- [ ] Auth flows: register, login, token refresh
- [ ] Core modules: expenses, bills, reminders, dashboard, insights

### Local K8s Development

Use [Tilt](https://tilt.dev) for live-reload K8s dev:

```bash
tilt up
```

This builds images, applies manifests, sets up port forwarding, and live-reloads on code changes.
