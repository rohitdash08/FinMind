# FinMind Deployment Guide

This guide covers all supported deployment methods for FinMind.

## Prerequisites

- Docker & Docker Compose (for local/compose deployments)
- A PostgreSQL 16+ database
- A Redis instance
- (Optional) Google Gemini API key for AI features

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET` | Yes | — | Secret for JWT signing |
| `GEMINI_API_KEY` | No | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name |
| `LOG_LEVEL` | No | `INFO` | Log level |

---

## 1. Docker Compose (Recommended for Self-Hosting)

The quickest way to run the full stack locally or on a VPS.

```bash
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

Services exposed:
- Backend API: `http://localhost:8000`
- Frontend (dev): `http://localhost:5173`
- Nginx reverse proxy: `http://localhost:8080`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

---

## 2. Kubernetes (Helm)

### Install with Helm

```bash
helm install finmind ./deploy/helm/finmind \
  --namespace finmind --create-namespace \
  --set secrets.postgresPassword=YOUR_PASSWORD \
  --set secrets.jwtSecret=YOUR_JWT_SECRET \
  --set secrets.geminiApiKey=YOUR_KEY
```

### Enable TLS

```yaml
# values-production.yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: finmind.example.com
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
        - finmind.example.com
```

```bash
helm upgrade finmind ./deploy/helm/finmind \
  --namespace finmind -f values-production.yaml
```

### Autoscaling

HPA is enabled by default. Configure in `values.yaml`:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

---

## 3. Kubernetes (Raw Manifests)

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.example.yaml  # Edit first!
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml
```

---

## 4. Local K8s Development (Tilt)

[Tilt](https://tilt.dev/) provides hot-reload for K8s development.

```bash
# Prerequisites: tilt, kubectl, a local cluster (minikube/kind/k3d)
tilt up
```

This will:
- Build images locally with live-sync (no full rebuilds)
- Deploy via Helm with dev settings (1 replica, no HPA)
- Port forward: backend `:8000`, frontend `:3000`, postgres `:5432`, redis `:6379`

---

## 5. One-Click Cloud Deployments

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?template=https://github.com/rohitdash08/FinMind)

Config: `railway.json`

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

Config: `render.yaml` — provisions backend, frontend, PostgreSQL, and Redis.

### Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

Config: `app.json` — provisions Heroku Postgres and Redis add-ons.

### Fly.io

```bash
fly launch          # Uses fly.toml
fly secrets set JWT_SECRET=your-secret GEMINI_API_KEY=your-key
fly deploy
```

Config: `fly.toml`

### DigitalOcean App Platform

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main)

Config: `.do/app.yaml`

---

## 6. CI/CD — Docker Image Publishing

Images are automatically built and pushed to GHCR on every push to `main` or version tag.

Workflow: `.github/workflows/docker-publish.yml`

Images:
- `ghcr.io/rohitdash08/finmind-backend:latest`
- `ghcr.io/rohitdash08/finmind-frontend:latest`

Tags follow semver (e.g., `v1.2.3` → `:1.2.3`, `:1.2`, `:latest`).

---

## Architecture

```
                    ┌─────────┐
                    │ Ingress │
                    └────┬────┘
                 ┌───────┴───────┐
                 │               │
           ┌─────▼─────┐  ┌─────▼─────┐
           │  Frontend  │  │  Backend   │
           │  (nginx)   │  │  (gunicorn)│
           └────────────┘  └─────┬──────┘
                           ┌─────┴──────┐
                     ┌─────▼───┐  ┌─────▼───┐
                     │ Postgres │  │  Redis   │
                     └──────────┘  └──────────┘
```
