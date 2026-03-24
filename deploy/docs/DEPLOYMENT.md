# FinMind Universal Deployment Guide

## Quick Start

### Docker Compose (Recommended for local/VPS)
```bash
cd deploy/docker
cp ../../.env.example ../../.env  # Edit with your values
docker compose -f docker-compose.prod.yml up -d --build
```
- Frontend: http://localhost
- Backend: http://localhost:8000
- Grafana: http://localhost:3000

### Kubernetes (Production)
```bash
cd deploy/scripts
./deploy-kubernetes.sh
```

### Tilt (Local K8s Dev)
```bash
cd deploy/tilt
tilt up
```
- Backend: http://localhost:8000 (port-forwarded)
- Frontend: http://localhost:3080 (port-forwarded)

## Platform-Specific Deployments

| Platform | Script | Prerequisites |
|----------|--------|---------------|
| Railway | `deploy-railway.sh` | `railway` CLI |
| Fly.io | `deploy-flyio.sh` | `flyctl` CLI |
| Render | `deploy-render.sh` | Render account + GitHub repo |
| Heroku | `deploy-heroku.sh` | `heroku` CLI |
| AWS ECS | `deploy-aws-ecs.sh` | `aws` CLI + configured credentials |
| GCP Cloud Run | `deploy-gcp-cloudrun.sh` | `gcloud` CLI + project |
| Azure | `deploy-azure.sh` | `az` CLI + subscription |
| DigitalOcean | `deploy-digitalocean.sh` | `doctl` CLI |
| Netlify | `deploy-netlify.sh` | `netlify-cli` (frontend only) |
| Vercel | `deploy-vercel.sh` | `vercel` CLI (frontend only) |
| Kubernetes | `deploy-kubernetes.sh` | `kubectl` + `helm` |

## Kubernetes Architecture

```
┌─────────────────────────────────────────────┐
│                  Ingress                     │
│           (TLS via cert-manager)             │
├──────────────────┬──────────────────────────┤
│    Frontend      │       Backend            │
│   (Nginx/React)  │   (Flask/Gunicorn)       │
│   Replicas: 2+   │   Replicas: 2+          │
│   HPA enabled    │   HPA enabled           │
├──────────────────┴──────────────────────────┤
│           PostgreSQL  │  Redis              │
│         (Persistent)  │ (In-memory)         │
├─────────────────────────────────────────────┤
│  Prometheus │ Grafana │ ServiceMonitor      │
└─────────────────────────────────────────────┘
```

## Helm Values Override Example
```bash
helm install finmind deploy/kubernetes/helm \
  --set ingress.hosts[0].host=myfinmind.com \
  --set autoscaling.maxReplicas=20 \
  --set resources.backend.limits.memory=1Gi
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| POSTGRES_USER | Yes | finmind | Database username |
| POSTGRES_PASSWORD | Yes | - | Database password |
| POSTGRES_DB | Yes | finmind | Database name |
| SECRET_KEY | Yes | - | Flask secret key |
| REDIS_URL | No | redis://redis:6379 | Redis connection |
| DATABASE_URL | No | (auto) | PostgreSQL connection |
