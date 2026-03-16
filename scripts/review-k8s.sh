#!/usr/bin/env sh
set -eu

CLUSTER_NAME="${FINMIND_KIND_CLUSTER:-finmind-review}"
NAMESPACE="${FINMIND_K8S_NAMESPACE:-finmind}"
RUN_TILT="${FINMIND_RUN_TILT_CI:-0}"
BACKEND_PORT_FORWARD_PID=""
FRONTEND_PORT_FORWARD_PID=""

cleanup_port_forwards() {
  if [ -n "$BACKEND_PORT_FORWARD_PID" ]; then
    kill "$BACKEND_PORT_FORWARD_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$FRONTEND_PORT_FORWARD_PID" ]; then
    kill "$FRONTEND_PORT_FORWARD_PID" >/dev/null 2>&1 || true
  fi
}

start_port_forwards() {
  kubectl -n "$NAMESPACE" port-forward svc/finmind-backend 18000:8000 >/dev/null 2>&1 &
  BACKEND_PORT_FORWARD_PID=$!
  kubectl -n "$NAMESPACE" port-forward svc/finmind-frontend 18081:80 >/dev/null 2>&1 &
  FRONTEND_PORT_FORWARD_PID=$!
}

delete_cluster() {
  kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
}

trap cleanup_port_forwards EXIT INT TERM

delete_cluster

docker build -t finmind-backend:ci packages/backend
docker build -t finmind-frontend:ci app

kind create cluster --name "$CLUSTER_NAME" --wait 120s
kind load docker-image finmind-backend:ci --name "$CLUSTER_NAME"
kind load docker-image finmind-frontend:ci --name "$CLUSTER_NAME"

helm upgrade --install finmind deploy/helm/finmind \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --timeout 10m0s \
  --set ingress.enabled=false \
  --set monitoring.enabled=false \
  --set backend.image.repository=finmind-backend \
  --set backend.image.tag=ci \
  --set backend.image.pullPolicy=IfNotPresent \
  --set frontend.image.repository=finmind-frontend \
  --set frontend.image.tag=ci \
  --set frontend.image.pullPolicy=IfNotPresent

kubectl rollout status deployment/finmind-backend -n "$NAMESPACE" --timeout=180s
kubectl rollout status deployment/finmind-frontend -n "$NAMESPACE" --timeout=180s

helm test finmind -n "$NAMESPACE" --logs

start_port_forwards
sleep 10
python3 scripts/smoke-deploy.py \
  --api-base-url http://127.0.0.1:18000 \
  --frontend-url http://127.0.0.1:18081

if [ "$RUN_TILT" = "1" ]; then
  tilt ci --timeout 10m
fi

delete_cluster
