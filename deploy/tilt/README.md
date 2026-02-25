# FinMind — Tilt Local K8s Development

## Overview

[Tilt](https://tilt.dev) provides a fast local Kubernetes development workflow with:
- Live-update (hot reload) for backend Python and frontend React code
- Automatic image rebuilds on file changes
- Port forwarding for all services
- Dependency-ordered startup (PostgreSQL → Redis → Backend → Frontend)
- Tilt dashboard at http://localhost:10350

## Prerequisites

1. [Tilt](https://docs.tilt.dev/install.html) installed
2. A local K8s cluster: [minikube](https://minikube.sigs.k8s.io/), [kind](https://kind.sigs.k8s.io/), or Docker Desktop Kubernetes
3. `kubectl` configured to point at your local cluster

## Quick Start

```bash
# 1. Create namespace and secrets
kubectl apply -f deploy/k8s/namespace.yaml
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml with real values
kubectl apply -f deploy/k8s/secrets.yaml

# 2. Start Tilt
tilt up
```

Tilt Dashboard opens at: http://localhost:10350

## Port Forwards

| Service | Local Port | Description |
|---------|-----------|-------------|
| Backend | 8000 | Flask API |
| Frontend | 5173 | Vite dev server (if using dev mode) |
| Nginx | 8080 | Reverse proxy |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache |

## Live Update

Changes to these files trigger automatic updates without full rebuilds:

| Path | Action |
|------|--------|
| `packages/backend/app/**` | Synced to container |
| `packages/backend/wsgi.py` | Synced to container |
| `packages/backend/requirements.txt` | Triggers `pip install` |
| `app/src/**` | Synced to container |
| `app/public/**` | Synced to container |
| `app/package.json` | Triggers `npm install` |

## Stopping

```bash
tilt down  # Stops all resources
```
