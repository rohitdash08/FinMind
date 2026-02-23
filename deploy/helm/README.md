# Deploy FinMind with Helm (Kubernetes)

## Prerequisites

- Kubernetes cluster (any cloud or local)
- Helm 3.x
- kubectl configured

## Quick Install

```bash
# Install with built-in PostgreSQL and Redis
helm install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgresql.auth.password=$(openssl rand -hex 16) \
  --set ingress.hosts[0].host=finmind.yourdomain.com
```

## With External Database

```bash
helm install finmind deploy/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set postgresql.enabled=false \
  --set redis.enabled=false \
  --set secrets.databaseUrl="postgresql+psycopg2://user:pass@host:5432/finmind" \
  --set secrets.redisUrl="redis://host:6379/0" \
  --set secrets.jwtSecret="your-secret"
```

## Features

- ✅ Helm charts with configurable values
- ✅ Ingress with TLS (cert-manager ready)
- ✅ HPA autoscaling (CPU + Memory)
- ✅ Health probes (liveness + readiness)
- ✅ Secret management
- ✅ Prometheus annotations for observability
- ✅ Init container for DB migration

## Customize

See `deploy/helm/finmind/values.yaml` for all configurable options.

## Upgrade

```bash
helm upgrade finmind deploy/helm/finmind --namespace finmind --reuse-values
```

## Uninstall

```bash
helm uninstall finmind --namespace finmind
```
