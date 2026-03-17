# FinMind Kubernetes Deployment

This folder provides a low-cost Kubernetes deployment path for:
- FinMind backend API
- PostgreSQL + Redis
- Nginx reverse proxy + metrics exporter
- Grafana OSS + Prometheus + Loki + Promtail + node-exporter

## 1. Prerequisites
- Kubernetes cluster (k3s, EKS, AKS, GKE, or kind for local)
- Ingress Nginx controller installed (`ingressClassName: nginx`)
- `kubectl` configured to target the cluster
- Backend image published (default in manifests: `ghcr.io/rohitdash08/finmind-backend:latest`)

## 2. Setup Secrets
1. Copy and edit secrets:
```bash
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
```
2. Update all secret values in `deploy/k8s/secrets.yaml`.

## 3. Apply Manifests
```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml
```

## 4. Validate
```bash
kubectl get pods -n finmind
kubectl get svc -n finmind
kubectl get ingress -n finmind
```

Check API health from cluster:
```bash
kubectl run curl -n finmind --rm -it --restart=Never --image=curlimages/curl -- \
  http://backend:8000/health
```

## 5. Port-forward (owner/admin access)
Grafana:
```bash
kubectl port-forward -n finmind svc/grafana 3000:3000
```
Prometheus:
```bash
kubectl port-forward -n finmind svc/prometheus 9090:9090
```

## 6. Notes
- `app-stack.yaml` uses in-cluster Postgres/Redis for low-cost deployment.
- `monitoring-stack.yaml` keeps retention conservative (Prometheus 14d, Loki 7d).
- For production, replace default hostnames (`api.finmind.local`, `grafana.finmind.local`) with real DNS.
- For production security, restrict Grafana ingress or remove ingress and use VPN/port-forward only.
