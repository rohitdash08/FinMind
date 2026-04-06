# FinMind - Local Kubernetes Development with Tilt

## Prerequisites
1. **Docker Desktop** (or equivalent) with Kubernetes enabled
2. **Tilt** - Install from https://docs.tilt.dev/install.html
3. **Helm** - Install from https://helm.sh/docs/intro/install/

## Quick Start
```bash
# From the project root:
tilt up

# Tilt will:
# 1. Build Docker images for backend and frontend
# 2. Deploy to local Kubernetes via Helm
# 3. Set up port forwards
# 4. Enable live reload for code changes

# Access:
# Frontend:  http://localhost:5173
# Backend:   http://localhost:8000
# Tilt UI:   http://localhost:10350
```

## How It Works
- **Tiltfile** in the project root orchestrates the local dev workflow
- Backend and frontend Docker images are built with live-update support
- Helm chart deploys all services (postgres, redis, backend, frontend)
- Code changes are synced into running containers without full rebuilds
- HPA and monitoring are disabled for local dev efficiency

## Stopping
```bash
tilt down
```
This tears down all Kubernetes resources created by Tilt.
