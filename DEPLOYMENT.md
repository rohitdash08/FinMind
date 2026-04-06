# FinMind Deployment Guide

Universal one-click deployment system for FinMind across Docker, Kubernetes, and all major cloud platforms.

## Quick Start

```bash
# One-command deploy (local Docker)
bash deploy/deploy.sh docker

# Production Docker
bash deploy/deploy.sh docker-prod

# Kubernetes via Helm
bash deploy/deploy.sh helm

# Local K8s development with Tilt
bash deploy/deploy.sh tilt
```

## Architecture Overview

```
+------------------+     +-----------------+     +------------------+
|  Frontend (SPA)  |---->|   Nginx/Ingress |---->|  Backend (Flask) |
|  React + Vite    |     |   Reverse Proxy |     |  Gunicorn        |
+------------------+     +-----------------+     +--------+---------+
                                                         |
                                          +--------------+--------------+
                                          |                             |
                                   +------v------+             +-------v------+
                                   |  PostgreSQL  |             |    Redis     |
                                   |  (Primary DB)|             |  (Cache/Queue)|
                                   +-------------+             +--------------+
```

## Supported Platforms

| Platform | Type | One-Click | Config Location |
|----------|------|-----------|-----------------|
| Docker Compose | Local/Production | `bash deploy/deploy.sh docker` | `docker-compose.yml` / `docker-compose.prod.yml` |
| Kubernetes (Helm) | Cloud-agnostic | `bash deploy/deploy.sh helm` | `deploy/helm/finmind/` |
| Tilt | Local K8s dev | `bash deploy/deploy.sh tilt` | `Tiltfile` |
| Railway | PaaS | [![Deploy](https://railway.app/button.svg)](https://railway.app/template/finmind) | `deploy/platforms/railway/` |
| Heroku | PaaS | [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy) | `deploy/platforms/heroku/` |
| Render | PaaS | [![Deploy](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy) | `deploy/platforms/render/` |
| Fly.io | PaaS | `bash deploy/deploy.sh flyio` | `deploy/platforms/flyio/` |
| DigitalOcean App | PaaS | `doctl apps create --spec ...` | `deploy/platforms/digitalocean-app/` |
| DigitalOcean Droplet | IaaS | `bash deploy/deploy.sh digitalocean-droplet` | `deploy/platforms/digitalocean-droplet/` |
| AWS ECS Fargate | Cloud | `bash deploy/deploy.sh aws-ecs` | `deploy/platforms/aws-ecs/` |
| AWS App Runner | Cloud | Via AWS Console/CLI | `deploy/platforms/aws-apprunner/` |
| GCP Cloud Run | Cloud | `bash deploy/deploy.sh gcp-cloudrun` | `deploy/platforms/gcp-cloudrun/` |
| Azure Container Apps | Cloud | `bash deploy/deploy.sh azure` | `deploy/platforms/azure-container-apps/` |
| Netlify | Frontend CDN | [![Deploy](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy) | `deploy/platforms/netlify/` |
| Vercel | Frontend CDN | [![Deploy](https://vercel.com/button)](https://vercel.com/new/clone) | `deploy/platforms/vercel/` |

---

## Docker Deployment

### Development
```bash
# Start all services with hot-reload
docker compose up -d

# Verify
curl http://localhost:8000/health
open http://localhost:5173
```

### Production
```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with production values

# Start production stack
docker compose -f docker-compose.prod.yml up -d
```

### Building Images
```bash
# Backend
docker build -t finmind-backend:latest -f packages/backend/Dockerfile packages/backend/

# Frontend
docker build -t finmind-frontend:latest -f app/Dockerfile app/
```

---

## Kubernetes Deployment

### Prerequisites
- `kubectl` configured with cluster access
- `helm` v3+ installed

### Helm Chart Install
```bash
# Install with defaults
helm upgrade --install finmind deploy/helm/finmind \
    --namespace finmind \
    --create-namespace

# Install with custom values
helm upgrade --install finmind deploy/helm/finmind \
    --namespace finmind \
    --create-namespace \
    -f deploy/helm/finmind/values.yaml \
    --set secrets.postgresPassword=your-strong-password \
    --set secrets.jwtSecret=your-jwt-secret \
    --set ingress.hosts[0].host=finmind.yourdomain.com

# Check status
kubectl get pods -n finmind
kubectl get svc -n finmind
kubectl get ingress -n finmind
```

### Helm Chart Features
- **Autoscaling (HPA)**: Backend scales 2-10 replicas based on CPU/memory
- **Ingress with TLS**: cert-manager integration for automatic HTTPS
- **Health Probes**: Readiness and liveness checks on all services
- **Secret Management**: Kubernetes Secrets for sensitive configuration
- **Network Policies**: Restrict inter-pod communication
- **Resource Limits**: CPU/memory requests and limits for all pods
- **Observability**: Optional Prometheus + Grafana + Loki stack

### Custom Values Example
```yaml
# custom-values.yaml
backend:
  replicaCount: 3
  autoscaling:
    enabled: true
    maxReplicas: 20

ingress:
  enabled: true
  className: nginx
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

secrets:
  postgresPassword: super-secret-password
  jwtSecret: your-256-bit-secret
```

---

## Tilt (Local K8s Development)

### Prerequisites
- Docker Desktop with Kubernetes enabled (or minikube/kind)
- [Tilt](https://docs.tilt.dev/install.html) installed

### Quick Start
```bash
# Start the dev environment
tilt up

# Access:
# Frontend:  http://localhost:5173
# Backend:   http://localhost:8000
# Tilt UI:   http://localhost:10350

# Stop and clean up
tilt down
```

### Features
- **Live Reload**: Code changes sync into running containers instantly
- **Helm Integration**: Uses the same Helm chart as production
- **Port Forwarding**: Automatic port forwards for all services
- **Resource Labels**: Organized view in Tilt UI (app vs infra)

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+psycopg2://finmind:finmind@postgres:5432/finmind` | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection string |
| `JWT_SECRET` | Yes | `change-me` | JWT signing secret (use 256-bit random) |
| `POSTGRES_USER` | Yes | `finmind` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | `finmind` | PostgreSQL password |
| `POSTGRES_DB` | Yes | `finmind` | PostgreSQL database name |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `GEMINI_API_KEY` | No | | Google Gemini API key for AI insights |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model to use |
| `VITE_API_URL` | Frontend | `http://localhost:8000` | Backend API URL for frontend |

---

## Health Checks & Verification

After deploying on any platform, verify the deployment:

```bash
# Backend health check
curl -f http://YOUR_HOST/health
# Expected: {"status": "ok"}

# Frontend reachable
curl -f http://YOUR_HOST/
# Expected: HTML content

# Database connected (via backend health)
curl -f http://YOUR_HOST/health
# Returns 200 only when DB + Redis are connected
```

---

## Monitoring & Observability

The Helm chart includes an optional monitoring stack:

```yaml
# Enable in values.yaml
monitoring:
  enabled: true
  prometheus:
    enabled: true
  grafana:
    enabled: true
  loki:
    enabled: true
```

- **Prometheus**: Metrics collection from backend, postgres, redis, nginx
- **Grafana**: Pre-configured dashboards at port 3000
- **Loki + Promtail**: Log aggregation
- **Exporters**: node-exporter, postgres-exporter, redis-exporter, nginx-exporter

---

## Security Best Practices

1. **Change all default passwords** in `.env` / `values.yaml` before production
2. **Enable TLS** via ingress annotations or platform-native HTTPS
3. **Use external secrets** (AWS Secrets Manager, GCP Secret Manager, etc.) in production
4. **Network policies** restrict inter-pod communication (Helm chart includes defaults)
5. **Resource limits** prevent runaway containers from affecting the cluster
6. **Health probes** ensure unhealthy containers are restarted automatically

---

## Troubleshooting

### Common Issues

**Backend won't start**
```bash
# Check logs
docker compose logs backend
# or
kubectl logs -n finmind -l app=backend
```

**Database connection refused**
```bash
# Ensure postgres is healthy
docker compose ps postgres
# or
kubectl get pods -n finmind -l app=postgres
```

**Frontend shows blank page**
- Check `VITE_API_URL` is set correctly
- Verify backend is reachable from the frontend's network
