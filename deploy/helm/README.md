# FinMind Helm Chart

Production-grade Helm chart for deploying FinMind on Kubernetes.

## Features

- Full application stack (Backend, Frontend, PostgreSQL, Redis)
- Nginx reverse proxy with load balancing
- Complete observability stack (Prometheus, Grafana, Loki, Promtail)
- Horizontal Pod Autoscaling (HPA) for backend and frontend
- TLS/HTTPS support with cert-manager integration
- Health probes (readiness, liveness, startup)
- Resource limits and requests
- ConfigMap and Secret management
- Multiple environment configurations (local, production)

## Prerequisites

- Kubernetes 1.24+
- Helm 3.10+
- kubectl configured for your cluster
- Ingress controller (nginx-ingress recommended)
- cert-manager (optional, for TLS)
- metrics-server (required for HPA)

## Quick Start

### 1. Add hosts entry (for local development)

```bash
echo "127.0.0.1 finmind.local api.finmind.local grafana.finmind.local" | sudo tee -a /etc/hosts
```

### 2. Create secrets file

```bash
cp deploy/helm/finmind/values.yaml deploy/helm/finmind/values-secrets.yaml
```

Edit `values-secrets.yaml` and fill in your secrets:
- `secrets.postgres.password`
- `secrets.jwt.secret`
- `secrets.grafana.adminPassword`
- `secrets.gemini.apiKey` (optional)

### 3. Install the chart

**Local development:**
```bash
helm install finmind ./deploy/helm/finmind \
  -f ./deploy/helm/finmind/values-local.yaml \
  -f ./deploy/helm/finmind/values-secrets.yaml
```

**Production:**
```bash
helm install finmind ./deploy/helm/finmind \
  -f ./deploy/helm/finmind/values-production.yaml \
  -f ./deploy/helm/finmind/values-secrets.yaml \
  --set certManager.email=your-email@example.com \
  --set ingress.hosts.api=api.yourdomain.com \
  --set ingress.hosts.frontend=yourdomain.com
```

### 4. Verify deployment

```bash
kubectl get pods -n finmind
kubectl get svc -n finmind
kubectl get ingress -n finmind
```

## Configuration

### Key Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.namespace` | Kubernetes namespace | `finmind` |
| `global.domain` | Base domain for ingress | `finmind.local` |
| `backend.replicaCount` | Number of backend replicas | `2` |
| `backend.autoscaling.enabled` | Enable HPA for backend | `true` |
| `backend.autoscaling.maxReplicas` | Maximum backend replicas | `10` |
| `frontend.enabled` | Deploy frontend | `true` |
| `ingress.tls.enabled` | Enable TLS | `false` |
| `certManager.enabled` | Use cert-manager for TLS | `false` |
| `monitoring.enabled` | Deploy monitoring stack | `true` |

### TLS Configuration

**With cert-manager:**
```yaml
ingress:
  tls:
    enabled: true
certManager:
  enabled: true
  issuer: letsencrypt-prod
  email: admin@yourdomain.com
```

**With existing certificates:**
```bash
kubectl create secret tls finmind-tls-api \
  --cert=path/to/cert.pem \
  --key=path/to/key.pem \
  -n finmind

helm install finmind ./deploy/helm/finmind \
  --set ingress.tls.enabled=true \
  --set ingress.tls.secretName=finmind-tls
```

### Autoscaling

The chart includes HPA for both backend and frontend:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
    targetMemoryUtilizationPercentage: 80
```

Ensure metrics-server is installed:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Upgrade

```bash
helm upgrade finmind ./deploy/helm/finmind \
  -f ./deploy/helm/finmind/values-production.yaml \
  -f ./deploy/helm/finmind/values-secrets.yaml
```

## Uninstall

```bash
helm uninstall finmind
kubectl delete namespace finmind
```

## Accessing Services

### Via Ingress (recommended)
- Frontend: https://finmind.local (or your configured domain)
- API: https://api.finmind.local
- Grafana: https://grafana.finmind.local

### Via Port Forward
```bash
kubectl port-forward -n finmind svc/frontend 8080:80
kubectl port-forward -n finmind svc/backend 8000:8000
kubectl port-forward -n finmind svc/grafana 3000:3000
```

## Monitoring

Grafana comes pre-configured with Prometheus and Loki datasources.

Default credentials:
- Username: `finmind_admin` (configurable)
- Password: Retrieved from secret

```bash
kubectl get secret -n finmind finmind-secrets \
  -o jsonpath="{.data.GRAFANA_ADMIN_PASSWORD}" | base64 -d
```

## Troubleshooting

### Pods not starting

```bash
kubectl describe pod -n finmind <pod-name>
kubectl logs -n finmind <pod-name>
```

### Database connection issues

```bash
kubectl run pg-test -n finmind --rm -it --restart=Never \
  --image=postgres:16 -- psql -h postgres -U finmind -d finmind
```

### Check HPA status

```bash
kubectl get hpa -n finmind
kubectl describe hpa backend-hpa -n finmind
```
