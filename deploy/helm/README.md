# FinMind Helm Chart

Production-grade Kubernetes deployment using Helm with full observability, autoscaling, and security best practices.

## Prerequisites

- Kubernetes cluster (1.24+)
- Helm 3.10+
- kubectl configured
- (Optional) Prometheus Operator for ServiceMonitor

## Quick Start

```bash
cd deploy/helm/finmind

# Add Bitnami repo for PostgreSQL and Redis
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Update chart dependencies
helm dependency update

# Install with generated secrets
helm install finmind . \
  --namespace finmind --create-namespace \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgresql.auth.password=$(openssl rand -base64 16)
```

## Configuration

### Required Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `secrets.jwtSecret` | JWT signing secret | (must be set) |
| `postgresql.auth.password` | PostgreSQL password | (must be set) |

### Optional Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `secrets.geminiApiKey` | Google Gemini API key | `""` |
| `backend.replicaCount` | Backend pod replicas | `2` |
| `backend.resources.limits.cpu` | CPU limit | `500m` |
| `backend.resources.limits.memory` | Memory limit | `512Mi` |
| `backend.autoscaling.enabled` | Enable HPA | `true` |
| `backend.autoscaling.minReplicas` | Min replicas | `2` |
| `backend.autoscaling.maxReplicas` | Max replicas | `10` |
| `ingress.enabled` | Enable Ingress | `true` |
| `ingress.className` | Ingress class | `nginx` |
| `ingress.hosts[0].host` | Ingress hostname | `api.finmind.example.com` |
| `postgresql.enabled` | Deploy PostgreSQL | `true` |
| `redis.enabled` | Deploy Redis | `true` |
| `metrics.enabled` | Enable Prometheus metrics | `true` |
| `networkPolicy.enabled` | Enable network policies | `false` |

### Full values.yaml example

```yaml
# Production configuration
backend:
  replicaCount: 3
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 200m
      memory: 512Mi
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 20
    targetCPUUtilizationPercentage: 60

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit-connections: "100"
  hosts:
    - host: api.finmind.io
      paths:
        - path: /
          pathType: Prefix
          service: backend
  tls:
    - secretName: finmind-tls
      hosts:
        - api.finmind.io

secrets:
  jwtSecret: "your-production-secret"
  geminiApiKey: "your-gemini-api-key"

postgresql:
  enabled: true
  auth:
    password: "strong-password"
  primary:
    persistence:
      size: 50Gi
    resources:
      limits:
        cpu: 2000m
        memory: 4Gi

redis:
  enabled: true
  master:
    persistence:
      size: 5Gi

metrics:
  enabled: true
  serviceMonitor:
    enabled: true

networkPolicy:
  enabled: true
```

## Installation Options

### Development

```bash
helm install finmind . \
  --namespace finmind-dev --create-namespace \
  --set backend.replicaCount=1 \
  --set backend.autoscaling.enabled=false \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgresql.auth.password=devpassword
```

### Staging

```bash
helm install finmind . \
  --namespace finmind-staging --create-namespace \
  --values values-staging.yaml \
  --set secrets.jwtSecret=$JWT_SECRET \
  --set postgresql.auth.password=$PG_PASSWORD
```

### Production

```bash
helm install finmind . \
  --namespace finmind --create-namespace \
  --values values-production.yaml \
  --set secrets.jwtSecret=$JWT_SECRET \
  --set secrets.geminiApiKey=$GEMINI_API_KEY \
  --set postgresql.auth.password=$PG_PASSWORD
```

## Upgrade

```bash
helm upgrade finmind . \
  --namespace finmind \
  --reuse-values \
  --set backend.image.tag=v1.2.0
```

## Uninstall

```bash
helm uninstall finmind --namespace finmind

# Clean up PVCs (data will be lost!)
kubectl delete pvc -n finmind --all
```

## Features

### Horizontal Pod Autoscaler (HPA)

Enabled by default. Scales based on CPU and memory:

```bash
kubectl get hpa -n finmind
```

### Pod Disruption Budget (PDB)

Ensures minimum availability during updates:

```bash
kubectl get pdb -n finmind
```

### Ingress with TLS

With cert-manager:

```yaml
ingress:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - secretName: finmind-tls
      hosts:
        - api.finmind.io
```

### Prometheus Metrics

Backend exposes `/metrics` endpoint. Enable ServiceMonitor for automatic scraping:

```yaml
metrics:
  serviceMonitor:
    enabled: true
```

### Network Policies

Restrict pod-to-pod traffic:

```yaml
networkPolicy:
  enabled: true
```

## Troubleshooting

### Check deployment status

```bash
helm status finmind -n finmind
kubectl get all -n finmind
```

### View logs

```bash
kubectl logs -n finmind -l app.kubernetes.io/name=finmind -f
```

### Check resource usage

```bash
kubectl top pods -n finmind
```

### Common Issues

**Pods stuck in Pending**: Check PVC binding and node resources
```bash
kubectl describe pod -n finmind <pod-name>
kubectl get pvc -n finmind
```

**Database connection errors**: Verify DATABASE_URL
```bash
kubectl exec -n finmind deployment/finmind-backend -- env | grep DATABASE
```

**Image pull errors**: Check image name and registry access
```bash
kubectl describe pod -n finmind <pod-name> | grep -A5 "Events"
```

## Chart Structure

```
deploy/helm/finmind/
├── Chart.yaml              # Chart metadata and dependencies
├── values.yaml             # Default configuration values
├── templates/
│   ├── _helpers.tpl        # Template helpers
│   ├── deployment.yaml     # Backend deployment
│   ├── service.yaml        # ClusterIP service
│   ├── ingress.yaml        # Ingress rules
│   ├── hpa.yaml            # Horizontal Pod Autoscaler
│   ├── pdb.yaml            # Pod Disruption Budget
│   ├── secret.yaml         # Secrets
│   ├── serviceaccount.yaml # Service account
│   ├── configmap.yaml      # Configuration
│   ├── networkpolicy.yaml  # Network policies
│   └── servicemonitor.yaml # Prometheus ServiceMonitor
└── charts/                 # Dependency charts (auto-populated)
    ├── postgresql/
    └── redis/
```
