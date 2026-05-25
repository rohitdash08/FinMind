# FinMind Kubernetes Deployment

This folder provides Kubernetes deployment options for FinMind:

## Deployment Options

### Option 1: Helm Chart (Recommended)

The Helm chart provides a production-grade deployment with:
- Horizontal Pod Autoscaling (HPA)
- TLS/HTTPS with cert-manager
- Configurable resource limits
- Multiple environment configurations

See [deploy/helm/README.md](../helm/README.md) for full documentation.

```bash
# Quick start with Helm
helm install finmind ./deploy/helm/finmind -f ./deploy/helm/finmind/values-local.yaml
```

### Option 2: Raw Manifests (This folder)

For simpler deployments or learning purposes, use raw manifests.

**Components:**
- FinMind backend API + Frontend
- PostgreSQL + Redis
- Nginx reverse proxy + metrics exporters
- Grafana OSS + Prometheus + Loki + Promtail + node-exporter

## Prerequisites

- Kubernetes cluster (k3s, EKS, AKS, GKE, or kind for local)
- Ingress Nginx controller installed (`ingressClassName: nginx`)
- `kubectl` configured to target the cluster
- Backend/Frontend images published (or built locally)
- metrics-server (for HPA): `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`

## Setup Secrets

1. Copy and edit secrets:
```bash
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
```
2. Update all secret values in `deploy/k8s/secrets.yaml`.

## Apply Manifests

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/frontend.yaml
kubectl apply -f deploy/k8s/hpa.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml
```

## Validate

```bash
kubectl get pods -n finmind
kubectl get svc -n finmind
kubectl get ingress -n finmind
kubectl get hpa -n finmind
```

Check API health from cluster:
```bash
kubectl run curl -n finmind --rm -it --restart=Never --image=curlimages/curl -- \
  http://backend:8000/health
```

## Port-forward (local access)

```bash
# Frontend
kubectl port-forward -n finmind svc/frontend 8080:80

# Backend API
kubectl port-forward -n finmind svc/backend 8000:8000

# Grafana
kubectl port-forward -n finmind svc/grafana 3000:3000

# Prometheus
kubectl port-forward -n finmind svc/prometheus 9090:9090
```

## TLS Configuration

For production TLS, install cert-manager and update the ingress annotations:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - <<EOF
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
```

Then update the ingress in `app-stack.yaml` with TLS configuration.

## Notes

- `app-stack.yaml` uses in-cluster Postgres/Redis for low-cost deployment
- `monitoring-stack.yaml` keeps retention conservative (Prometheus 14d, Loki 7d)
- For production, replace default hostnames with real DNS
- For production security, restrict Grafana ingress or use VPN/port-forward only
- HPA requires metrics-server to be installed in the cluster
