#!/bin/bash
# FinMind - Generic Kubernetes Deployment
set -euo pipefail
NAMESPACE=${NAMESPACE:-finmind}
RELEASE=${RELEASE:-finmind}
echo "☸️ Deploying FinMind to Kubernetes..."
kubectl create namespace $NAMESPACE 2>/dev/null || true
helm upgrade --install $RELEASE ../kubernetes/helm \
  --namespace $NAMESPACE \
  --set secrets.secretKey=$(openssl rand -hex 32) \
  --wait --timeout 300s
echo "✅ Deployed! Check: kubectl get pods -n $NAMESPACE"
