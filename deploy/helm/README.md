# FinMind Helm Chart (Milestone for Issue #144)

This chart packages the existing Kubernetes app stack into a reusable release unit.

## Scope of this milestone

- ✅ Helm chart for FinMind core stack (backend, postgres, redis, nginx, exporters)
- ✅ Ingress and HPA support via values
- ✅ Keeps existing secret model (`finmind-secrets`) to avoid breaking operators
- ✅ Tilt workflow for local Kubernetes iteration

This is a **shippable subset** toward the larger universal one-click objective, without claiming all platform integrations are complete.

## Prerequisites

- Kubernetes cluster (kind/k3d/minikube/EKS/GKE/AKS)
- Helm 3
- Secret created from `deploy/k8s/secrets.example.yaml` as `finmind-secrets`

## Install

```bash
helm upgrade --install finmind deploy/helm/finmind \
  --namespace finmind --create-namespace
```

## Validate

```bash
kubectl get pods -n finmind
kubectl get svc -n finmind
kubectl get ingress -n finmind
```

## Key values

- `images.backend`
- `ingress.enabled`, `ingress.host`, `ingress.className`
- `hpa.enabled`, `hpa.minReplicas`, `hpa.maxReplicas`
- `postgres.storage`

## Tilt (local K8s dev)

From repository root:

```bash
tilt up
```

Tilt installs/updates the Helm release and forwards backend port `8000`.
