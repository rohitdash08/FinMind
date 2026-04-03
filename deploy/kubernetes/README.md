# FinMind Kubernetes Deployment

## Prerequisites
- kubectl (v1.28+)
- helm (v3.12+)
- A running Kubernetes cluster
- [Optional] Tilt for local development

## Quick Start

### 1. Create namespace
kubectl apply -f namespace.yaml

### 2. Install with Helm
helm install finmind ../helm/finmind \
  --namespace finmind \
  --set secrets.jwtSecret=$(openssl rand -hex 32) \
  --set postgres.password=$(openssl rand -hex 16) \
  --set ingress.hosts[0].host=finmind.yourdomain.com

### 3. Verify deployment
kubectl get pods -n finmind
kubectl port-forward svc/finmind-backend 8000:8000 -n finmind
curl http://localhost:8000/health

## TLS with cert-manager

### Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

### Create ClusterIssuer
Apply a ClusterIssuer for Let's Encrypt:
```yaml
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
```

## Scaling
HPA is enabled by default (2-10 replicas, 50% CPU target).
Manual scaling: `kubectl scale deployment finmind-backend --replicas=5 -n finmind`

## Monitoring
- Liveness probe: GET /health (every 20s)
- Readiness probe: GET /health (every 10s)
- Prometheus metrics available at /metrics

## Tilt (Local Development)
```bash
tilt up
```
Access at http://localhost:8000
