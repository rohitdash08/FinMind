# Tilt Development Loop

This repository includes Docker Compose and Kubernetes manifests. The root `Tiltfile` adds the missing local Kubernetes development loop for the universal deployment path.

## Prerequisites

- Docker
- A local Kubernetes cluster using one of:
  - `kind-kind`
  - `kind-finmind`
  - `minikube`
  - `docker-desktop`
- `kubectl`
- `tilt`
- Node 20 for the local frontend dev server

## Start

```bash
tilt up
```

The Tiltfile will:

- create `deploy/k8s/secrets.yaml` from `deploy/k8s/secrets.example.yaml` when a local secrets file is missing
- build `ghcr.io/rohitdash08/finmind-backend` from `packages/backend`
- apply `deploy/k8s/namespace.yaml`, `deploy/k8s/secrets.yaml`, `deploy/k8s/app-stack.yaml`, and `deploy/k8s/monitoring-stack.yaml`
- live-sync backend source and tests into the backend container
- run the frontend Vite dev server as a Tilt local resource
- expose useful local ports

## Local URLs

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Nginx proxy: http://localhost:8080
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Loki: http://localhost:3100

## Validate

```bash
kubectl get pods -n finmind
curl http://localhost:8000/health
```

For a clean teardown:

```bash
tilt down
```
