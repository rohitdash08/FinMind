#!/usr/bin/env sh
set -eu

RELEASE_NAME="${1:-finmind}"
NAMESPACE="${2:-finmind}"
VALUES_FILE="${3:-}"

echo "Deploying FinMind via Helm..."
echo "  Release: $RELEASE_NAME"
echo "  Namespace: $NAMESPACE"

# Create namespace if it doesn't exist
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Build helm command
HELM_CMD="helm upgrade --install $RELEASE_NAME ./deploy/helm/finmind \
  --namespace $NAMESPACE \
  --wait \
  --timeout 5m"

if [ -n "$VALUES_FILE" ]; then
  HELM_CMD="$HELM_CMD -f $VALUES_FILE"
fi

echo "Running: $HELM_CMD"
eval "$HELM_CMD"

echo ""
echo "Deployment complete. Checking rollout status..."
kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-finmind-backend --timeout=120s
echo "Backend is ready."

echo ""
echo "Services:"
kubectl -n "$NAMESPACE" get svc
echo ""
echo "Pods:"
kubectl -n "$NAMESPACE" get pods
