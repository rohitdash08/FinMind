# FinMind — Helm Chart Deployment

## Overview

Production-grade Kubernetes deployment with:
- Backend (Flask/Gunicorn) + Frontend (React/Nginx) + Nginx reverse proxy
- PostgreSQL 16 + Redis 7 (in-cluster or external)
- HPA autoscaling (2–10 replicas)
- Ingress with TLS (cert-manager)
- Full monitoring stack: Prometheus, Grafana, Loki, Promtail
- Exporters: Node, PostgreSQL, Redis, Nginx
- External Secrets Operator support
- Health probes (readiness + liveness)
- Resource limits and requests

## Prerequisites

- Kubernetes cluster (1.24+)
- Helm 3.x
- kubectl configured
- (Optional) cert-manager for TLS
- (Optional) nginx-ingress controller

## Quick Start

```bash
# Install with defaults
helm install finmind deploy/helm/finmind -n finmind --create-namespace

# Install with custom values
helm install finmind deploy/helm/finmind -n finmind --create-namespace \
  --set secrets.JWT_SECRET=$(openssl rand -hex 32) \
  --set secrets.POSTGRES_PASSWORD=$(openssl rand -hex 16) \
  --set ingress.hosts[0].host=finmind.yourdomain.com

# Upgrade
helm upgrade finmind deploy/helm/finmind -n finmind

# Uninstall
helm uninstall finmind -n finmind
```

## Configuration

All values are in `values.yaml`. Key sections:

| Section | Description |
|---------|-------------|
| `backend` | Replicas, image, resources, probes |
| `frontend` | Frontend image and resources |
| `postgres` | In-cluster PostgreSQL (disable for external) |
| `redis` | In-cluster Redis (disable for external) |
| `ingress` | Hostname, TLS, cert-manager |
| `hpa` | Autoscaling min/max/target |
| `monitoring` | Prometheus, Grafana, Loki, exporters |
| `secrets` | Credentials (override with `--set`) |
| `externalSecrets` | External Secrets Operator integration |

## Using External Databases

```yaml
# values-external-db.yaml
postgres:
  enabled: false
redis:
  enabled: false
secrets:
  POSTGRES_USER: myuser
  POSTGRES_PASSWORD: mypassword
  POSTGRES_DB: finmind
```

Then override the DATABASE_URL in the backend config.

## Monitoring

Enable/disable individual monitoring components:

```yaml
monitoring:
  prometheus:
    enabled: true
  grafana:
    enabled: true
    ingress:
      enabled: true
      host: grafana.finmind.example.com
  loki:
    enabled: true
  promtail:
    enabled: true
```

Access Grafana at the configured ingress host. Default credentials: `finmind_admin` / `change-me-admin-password`
