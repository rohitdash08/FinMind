# FinMind Helm Chart

Production-ready Helm chart for deploying FinMind on Kubernetes.

## Features

- 🚀 **Production-Ready**: Optimized for production workloads
- 📈 **Auto-Scaling**: HPA for backend and frontend
- 🔒 **Secure**: TLS/HTTPS support with cert-manager
- 💾 **Persistent**: StatefulSet for PostgreSQL with PVC
- 🔍 **Observable**: Prometheus ServiceMonitor integration
- 🛡️ **Resilient**: PodDisruptionBudget for safe updates
- ⚙️ **Configurable**: Extensive values.yaml customization

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- PV provisioner support (for PostgreSQL persistence)
- Ingress controller (nginx recommended)
- cert-manager (optional, for TLS)
- Prometheus Operator (optional, for monitoring)

## Installation

### Quick Install

```bash
helm install finmind . \
  --namespace finmind \
  --create-namespace \
  --set backend.secrets.JWT_SECRET='your-secret-key'
```

### Production Install

```bash
# 1. Create custom values
cat > production-values.yaml <<EOF
backend:
  replicaCount: 3
  secrets:
    JWT_SECRET: "your-production-secret"
    OPENAI_API_KEY: "your-openai-key"
  resources:
    requests:
      memory: "512Mi"
      cpu: "500m"
    limits:
      memory: "1Gi"
      cpu: "1000m"

frontend:
  replicaCount: 2

postgresql:
  persistence:
    size: 20Gi
  auth:
    password: "your-db-password"

ingress:
  enabled: true
  hosts:
    - host: finmind.yourdomain.com
      paths:
        - path: /api
          pathType: Prefix
          backend: backend
        - path: /
          pathType: Prefix
          backend: frontend
  tls:
    - secretName: finmind-tls
      hosts:
        - finmind.yourdomain.com

monitoring:
  enabled: true
EOF

# 2. Install
helm install finmind . \
  -f production-values.yaml \
  --namespace finmind \
  --create-namespace
```

## Configuration

### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.replicaCount` | Number of backend replicas | `2` |
| `backend.image.repository` | Backend image repository | `finmind/backend` |
| `backend.image.tag` | Backend image tag | `latest` |
| `backend.secrets.JWT_SECRET` | JWT secret key | `""` |
| `backend.autoscaling.enabled` | Enable HPA for backend | `true` |
| `backend.autoscaling.minReplicas` | Min replicas for HPA | `2` |
| `backend.autoscaling.maxReplicas` | Max replicas for HPA | `10` |
| `frontend.replicaCount` | Number of frontend replicas | `2` |
| `postgresql.enabled` | Deploy PostgreSQL | `true` |
| `postgresql.persistence.enabled` | Enable PostgreSQL persistence | `true` |
| `postgresql.persistence.size` | PVC size for PostgreSQL | `10Gi` |
| `redis.enabled` | Deploy Redis | `true` |
| `ingress.enabled` | Enable ingress | `true` |
| `ingress.className` | Ingress class name | `nginx` |
| `monitoring.enabled` | Enable monitoring | `true` |

### Complete Values

See [values.yaml](./values.yaml) for all available configuration options.

## Upgrading

```bash
# Upgrade with new values
helm upgrade finmind . \
  -f production-values.yaml \
  --namespace finmind

# Rollback if needed
helm rollback finmind --namespace finmind
```

## Uninstalling

```bash
# Uninstall release
helm uninstall finmind --namespace finmind

# Delete namespace and PVCs
kubectl delete namespace finmind
```

## Advanced Configuration

### Custom Database

Use external PostgreSQL:

```yaml
postgresql:
  enabled: false

backend:
  env:
    DATABASE_URL: "postgresql://user:pass@external-host:5432/finmind"
```

### Custom Redis

Use external Redis:

```yaml
redis:
  enabled: false

backend:
  env:
    REDIS_URL: "redis://external-redis:6379/0"
```

### TLS with cert-manager

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

# Enable in values.yaml
ingress:
  enabled: true
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  tls:
    - secretName: finmind-tls
      hosts:
        - finmind.yourdomain.com
```

### Prometheus Monitoring

```bash
# Install Prometheus Operator
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace

# Enable in values.yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n finmind
kubectl describe pod -n finmind <pod-name>
kubectl logs -n finmind <pod-name>
```

### Check Services

```bash
kubectl get svc -n finmind
kubectl describe svc -n finmind finmind-backend
```

### Test Database Connection

```bash
kubectl exec -n finmind finmind-postgresql-0 -- psql -U finmind -d finmind -c "SELECT 1"
```

### Check Ingress

```bash
kubectl get ingress -n finmind
kubectl describe ingress -n finmind finmind
```

### View Events

```bash
kubectl get events -n finmind --sort-by='.lastTimestamp'
```

## Development

### Local Testing with Tilt

See [Tiltfile](../../../../Tiltfile) in repository root.

```bash
tilt up
```

### Template Rendering

```bash
# Render templates locally
helm template finmind . \
  -f values.yaml \
  --namespace finmind
```

### Lint Chart

```bash
helm lint .
```

## Architecture

```
┌─────────────────────────────────────────┐
│           Ingress (HTTPS/TLS)           │
│         finmind.yourdomain.com          │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌──────────┐    ┌──────────────┐
│ Frontend │    │   Backend    │
│ (Nginx)  │    │  (Gunicorn)  │
│   x2     │    │     x2+      │
└──────────┘    └───────┬──────┘
                        │
            ┌───────────┴────────┐
            │                    │
            ▼                    ▼
    ┌──────────────┐    ┌──────────┐
    │  PostgreSQL  │    │  Redis   │
    │ (StatefulSet)│    │ (Deploy) │
    │     PVC      │    │          │
    └──────────────┘    └──────────┘
```

## Security

- Non-root containers with security contexts
- Read-only root filesystems where possible
- Secrets managed via Kubernetes Secrets
- Network policies (optional)
- PodSecurityPolicy/PodSecurityStandards compatible

## License

MIT License - see [LICENSE](../../../../LICENSE) for details
