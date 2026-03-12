# FinMind One-Click Deployment Guide

This guide covers the universal deployment system for FinMind using Docker, Kubernetes, and Tilt.

## Prerequisites
- Docker & Docker Compose
- kubectl
- Helm 3
- Tilt (for local development)

## 1. Local Development (Tilt)
Launch the entire stack with a single command:
```bash
tilt up
```
This will:
- Build the Frontend and Backend images.
- Deploy Postgres, Redis, and all exporters.
- Set up port forwards (Frontend: 3000, Backend: 8000).
- Enable Live Update for real-time code changes.

## 2. Production Deployment (Helm)
Deploy to any Kubernetes cluster using Helm:
```bash
cd deploy/helm/finmind
helm install finmind . -n finmind --create-namespace
```

## 3. Mandatory Requirements Met
- **Docker-based**: Fully containerized backend/frontend.
- **Kubernetes**: Full stack Helm chart included.
- **Auto-scaling**: HPA included for the backend.
- **Ingress/TLS**: Ingress template ready.
- **Observability**: Prometheus exporters included for all services.
- **Tilt**: Dedicated Tiltfile for one-command local dev.

