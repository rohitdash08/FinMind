#!/usr/bin/env bash
# FinMind — Universal One-Click Deployment Script
# Usage: ./deploy/one-click.sh [platform]
# Platforms: docker | k8s | helm | railway | render | fly | heroku | do
set -euo pipefail

PLATFORM="${1:-docker}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

info()  { echo -e "\033[1;34m[FinMind]\033[0m $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

case "$PLATFORM" in
  docker)
    info "Starting FinMind with Docker Compose..."
    cd "$ROOT"
    cp -n .env.example .env 2>/dev/null || true
    docker compose up -d --build
    ok "FinMind is running at http://localhost:3000 (frontend) and http://localhost:8000 (backend)"
    ;;

  k8s)
    info "Deploying to Kubernetes..."
    command -v kubectl &>/dev/null || error "kubectl not found"
    kubectl apply -f "$ROOT/deploy/k8s/namespace.yaml"
    kubectl apply -f "$ROOT/deploy/k8s/app-stack.yaml"
    kubectl apply -f "$ROOT/deploy/k8s/monitoring-stack.yaml"
    kubectl rollout status deployment/finmind-backend -n finmind
    ok "Deployed to Kubernetes"
    ;;

  helm)
    info "Deploying with Helm..."
    command -v helm &>/dev/null || error "helm not found"
    helm upgrade --install finmind "$ROOT/deploy/helm/finmind" \
      --namespace finmind --create-namespace \
      --wait --timeout 5m
    ok "Helm release 'finmind' deployed"
    ;;

  tilt)
    info "Starting Tilt dev environment..."
    command -v tilt &>/dev/null || error "tilt not found (https://tilt.dev)"
    cd "$ROOT" && tilt up
    ;;

  railway)
    info "Deploying to Railway..."
    command -v railway &>/dev/null || error "railway CLI not found"
    cd "$ROOT" && railway up
    ;;

  render)
    info "Render deployment — push to git and Render auto-deploys from render.yaml"
    ok "See deploy/platforms/render.yaml for config"
    ;;

  fly)
    info "Deploying to Fly.io..."
    command -v fly &>/dev/null || error "fly CLI not found"
    cd "$ROOT" && fly deploy --config deploy/platforms/fly.toml
    ;;

  heroku)
    info "Deploying to Heroku..."
    command -v heroku &>/dev/null || error "heroku CLI not found"
    heroku container:push web -a "${HEROKU_APP_NAME:-finmind}"
    heroku container:release web -a "${HEROKU_APP_NAME:-finmind}"
    ok "Deployed to Heroku"
    ;;

  do)
    info "Deploying to DigitalOcean App Platform..."
    command -v doctl &>/dev/null || error "doctl not found"
    doctl apps create --spec deploy/platforms/do-app.yaml
    ok "DigitalOcean App created"
    ;;

  *)
    echo "Usage: $0 [docker|k8s|helm|tilt|railway|render|fly|heroku|do]"
    exit 1
    ;;
esac
