# FinMind Tilt Development Environment

Tilt provides a streamlined local Kubernetes development workflow with live code reloading.

## Prerequisites

- Docker Desktop with Kubernetes enabled, or:
  - kind (`kind create cluster`)
  - minikube (`minikube start`)
  - k3d (`k3d cluster create`)
- [Tilt](https://tilt.dev/) installed
- kubectl configured for your local cluster

## Quick Start

### 1. Start your local Kubernetes cluster

**Docker Desktop:**
Enable Kubernetes in Docker Desktop settings.

**kind:**
```bash
kind create cluster --name finmind
kubectl cluster-info --context kind-finmind
```

**minikube:**
```bash
minikube start --memory=4096 --cpus=2
```

### 2. Start Tilt

From the project root:

```bash
tilt up
```

This will:
1. Build Docker images for backend and frontend
2. Deploy PostgreSQL and Redis
3. Deploy the backend with live reload
4. Deploy the frontend with hot module replacement
5. Set up port forwarding automatically

### 3. Access the application

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **Tilt UI:** http://localhost:10350

### 4. Development Workflow

**Live Reload:**
- Backend: Edit files in `packages/backend/app/` - changes sync automatically
- Frontend: Edit files in `app/src/` - Vite hot reload handles updates

**Run Tests:**
- Press `t` in Tilt UI to trigger tests
- Or click on `backend-tests` / `frontend-tests` resources

**View Logs:**
- Press `s` in Tilt UI for streaming logs
- Click on any resource to see its logs

**Restart a Service:**
- Press `r` while a resource is selected

### 5. Stop Development

```bash
tilt down
```

## Tilt UI

The Tilt UI at http://localhost:10350 provides:

- Resource status and health
- Build logs and timing
- Port forward management
- Log streaming
- One-click restarts

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Tilt UI (:10350)                     │
└─────────────────────────────────────────────────────────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
┌─────────┐         ┌──────────┐          ┌───────────┐
│Frontend │         │ Backend  │          │ Postgres  │
│ :5173   │────────▶│  :8000   │─────────▶│   :5432   │
│(Vite HMR)         │(gunicorn)│          │           │
└─────────┘         └──────────┘          └───────────┘
                           │
                           ▼
                    ┌───────────┐
                    │   Redis   │
                    │   :6379   │
                    └───────────┘
```

## Customization

### Change port forwards

Edit the `Tiltfile`:
```python
k8s_resource(
    'backend',
    port_forwards='9000:8000',  # Change from 8000 to 9000
)
```

### Add environment variables

Edit the ConfigMap in `Tiltfile`:
```python
data:
  LOG_LEVEL: DEBUG
  MY_NEW_VAR: value
```

### Enable monitoring stack

For local monitoring, you can add Prometheus/Grafana by uncommenting the monitoring section in the Tiltfile or deploying via Helm:

```bash
helm install finmind ./deploy/helm/finmind \
  -f ./deploy/helm/finmind/values-local.yaml \
  --set monitoring.enabled=true
```

## Troubleshooting

### Images not building

```bash
# Check Docker is running
docker info

# Rebuild manually
docker build -t finmind-backend ./packages/backend
```

### Pods stuck in Pending

```bash
# Check events
kubectl get events -n finmind --sort-by='.lastTimestamp'

# Check node resources
kubectl describe nodes
```

### Database connection refused

```bash
# Check postgres is running
kubectl get pods -n finmind -l app=postgres

# Check logs
kubectl logs -n finmind -l app=postgres
```

### Port already in use

```bash
# Find and kill process using the port
lsof -i :8000
kill -9 <PID>

# Or change the port in Tiltfile
```
