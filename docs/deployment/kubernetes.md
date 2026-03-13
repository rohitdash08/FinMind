# Kubernetes Deployment Guide

## Prerequisites
- Kubernetes cluster (1.24+)
- `kubectl` configured
- `helm` 3.x (for Helm deployment)
- Container registry with built images

## Option 1: Raw Manifests
```bash
# Create namespace and secrets
kubectl apply -f deploy/k8s/namespace.yaml
# Copy and edit secrets
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# Edit secrets.yaml with base64-encoded values
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml
```

## Option 2: Helm Chart (Recommended)
```bash
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind --create-namespace \
  --set secrets.jwtSecret="$(openssl rand -hex 32)" \
  --set secrets.postgresPassword="$(openssl rand -hex 16)" \
  --set backend.image.repository=your-registry/finmind-backend \
  --set frontend.image.repository=your-registry/finmind-frontend
```

### Helm Features
- **HPA**: Auto-scales backend (2-10 replicas based on CPU)
- **Ingress**: TLS via cert-manager with Let's Encrypt
- **ServiceMonitor**: Prometheus-operator integration
- **Health Probes**: Readiness and liveness on all services
- **External Secrets**: Annotations ready for sealed-secrets/external-secrets

### Custom Values
```bash
helm upgrade --install finmind deploy/helm/finmind \
  -f my-values.yaml --namespace finmind
```

## Local Development with Tilt
```bash
tilt up
```

## Verification
```bash
kubectl -n finmind get pods
kubectl -n finmind port-forward svc/backend 8000:8000
curl http://localhost:8000/health
```
