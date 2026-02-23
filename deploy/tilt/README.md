# FinMind - Local Kubernetes Development with Tilt

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Tilt](https://docs.tilt.dev/install.html)
- A local Kubernetes cluster (any one of):
  - [minikube](https://minikube.sigs.k8s.io/docs/start/)
  - [kind](https://kind.sigs.k8s.io/docs/user/quick-start/)
  - [k3d](https://k3d.io/)
  - Docker Desktop Kubernetes

## Quick Start

```bash
# Start a local K8s cluster (example with kind)
kind create cluster --name finmind

# Start Tilt
tilt up

# Open Tilt dashboard
# → http://localhost:10350
```

## What Tilt Provides

- **Live reload**: Edit Python/React code → auto-syncs to running containers
- **Port forwarding**: 
  - Frontend: `http://localhost:5173`
  - Backend: `http://localhost:8000`
  - PostgreSQL: `localhost:5432`
  - Redis: `localhost:6379`
- **Log aggregation**: All service logs in Tilt UI
- **Health monitoring**: Visual status of all services

## Architecture

```
Tilt Dashboard (localhost:10350)
├── postgres (port 5432)
├── redis (port 6379)
├── finmind-api (port 8000) ← live-update Python files
└── finmind-web (port 5173) ← live-update React/Vite HMR
```

## Usage

```bash
# Start all services
tilt up

# Start specific services only
tilt up -- finmind-api postgres redis

# Tear down
tilt down

# Clean up cluster
kind delete cluster --name finmind
```

## Live Updates

| File Change | Action |
|---|---|
| `packages/backend/app/**` | Synced to container, auto-reload via gunicorn |
| `packages/backend/requirements.txt` | Runs `pip install` in container |
| `app/src/**` | Synced to container, Vite HMR instant refresh |
| `app/package.json` | Runs `npm install` in container |

## Troubleshooting

- **Pod stuck in CrashLoopBackOff**: Check logs in Tilt UI, usually DB not ready
- **Port conflict**: Change port forwards in `Tiltfile`
- **Slow builds**: Ensure Docker has enough resources (4GB+ RAM recommended)
