#!/usr/bin/env bash
# FinMind — Universal One-Click Deployment Script
#
# Usage:
#   ./deploy.sh <platform> [options]
#
# Platforms:
#   local          — Docker Compose (default, no cloud account needed)
#   k8s            — Kubernetes with existing cluster (kubectl must be configured)
#   helm           — Kubernetes via Helm chart
#   tilt           — Local K8s dev with Tilt (hot reload)
#   aws            — AWS ECS Fargate
#   gcp            — GCP Cloud Run
#   azure          — Azure Container Apps
#   railway        — Railway (requires railway CLI)
#   render         — Render (Blueprint via API or dashboard)
#   fly            — Fly.io
#   digitalocean   — DigitalOcean App Platform
#   netlify        — Netlify (frontend only)
#   vercel         — Vercel (frontend only)
#
# Examples:
#   ./deploy.sh local                        # Start with Docker Compose
#   ./deploy.sh k8s                          # Deploy to current kubectl context
#   ./deploy.sh helm --namespace finmind     # Deploy via Helm
#   ./deploy.sh gcp PROJECT_ID=my-project    # GCP Cloud Run
#   ./deploy.sh aws                          # AWS ECS Fargate

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date -u +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

PLATFORM="${1:-local}"
shift || true

banner() {
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  FinMind — Deploying to: ${YELLOW}${PLATFORM}${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

check_tool() {
  command -v "$1" &>/dev/null || die "Required tool not found: $1. Install it and retry."
}

# ─── local ──────────────────────────────────────────────────────────────────
deploy_local() {
  check_tool docker
  check_tool docker-compose || check_tool docker  # docker compose v2

  [[ -f "$REPO_ROOT/.env" ]] || {
    warn ".env not found — copying from .env.example"
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    warn "Edit .env and set your secrets, then re-run."
    exit 0
  }

  log "Starting FinMind with Docker Compose..."
  cd "$REPO_ROOT"
  docker compose up -d --build
  ok "FinMind is running."
  echo ""
  echo "  Frontend:  http://localhost:5173"
  echo "  Backend:   http://localhost:8000/health"
  echo "  Grafana:   http://localhost:3000"
  echo ""
  echo "  Logs:  docker compose logs -f backend"
  echo "  Stop:  docker compose down"
}

# ─── k8s ────────────────────────────────────────────────────────────────────
deploy_k8s() {
  check_tool kubectl
  NAMESPACE="${NAMESPACE:-finmind}"

  [[ -f "$REPO_ROOT/deploy/k8s/secrets.example.yaml" ]] && \
    warn "Remember to apply your secrets: kubectl apply -f deploy/k8s/secrets.example.yaml -n $NAMESPACE"

  log "Creating namespace $NAMESPACE..."
  kubectl apply -f "$REPO_ROOT/deploy/k8s/namespace.yaml"

  log "Applying Kubernetes manifests..."
  kubectl apply -f "$REPO_ROOT/deploy/k8s/app-stack.yaml" -n "$NAMESPACE"
  kubectl apply -f "$REPO_ROOT/deploy/k8s/monitoring-stack.yaml" -n "$NAMESPACE" 2>/dev/null || true

  log "Waiting for rollout..."
  kubectl rollout status deployment/backend -n "$NAMESPACE" --timeout=300s
  kubectl rollout status deployment/frontend -n "$NAMESPACE" --timeout=120s 2>/dev/null || true

  ok "Kubernetes deployment complete."
  kubectl get pods -n "$NAMESPACE"
}

# ─── helm ───────────────────────────────────────────────────────────────────
deploy_helm() {
  check_tool helm
  check_tool kubectl
  RELEASE="${HELM_RELEASE:-finmind}"
  NAMESPACE="${NAMESPACE:-finmind}"

  log "Deploying via Helm (release=$RELEASE, namespace=$NAMESPACE)..."
  helm upgrade --install "$RELEASE" "$REPO_ROOT/deploy/helm/finmind" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --wait \
    --timeout 10m \
    "$@"

  ok "Helm deployment complete."
  helm status "$RELEASE" -n "$NAMESPACE"
}

# ─── tilt ───────────────────────────────────────────────────────────────────
deploy_tilt() {
  check_tool tilt
  check_tool kubectl
  log "Starting Tilt local development environment..."
  cd "$REPO_ROOT"
  tilt up
}

# ─── aws ────────────────────────────────────────────────────────────────────
deploy_aws() {
  check_tool aws
  bash "$REPO_ROOT/deploy/platforms/aws/deploy.sh" "$@"
}

# ─── gcp ────────────────────────────────────────────────────────────────────
deploy_gcp() {
  check_tool gcloud
  bash "$REPO_ROOT/deploy/platforms/gcp/deploy.sh" "$@"
}

# ─── azure ──────────────────────────────────────────────────────────────────
deploy_azure() {
  check_tool az
  bash "$REPO_ROOT/deploy/platforms/azure/deploy.sh" "$@"
}

# ─── railway ─────────────────────────────────────────────────────────────────
deploy_railway() {
  check_tool railway
  log "Deploying backend to Railway..."
  cd "$REPO_ROOT"
  railway up --service finmind-backend
  ok "Railway deployment triggered. Check dashboard for status."
}

# ─── render ──────────────────────────────────────────────────────────────────
deploy_render() {
  log "Render Blueprint deployment"
  echo ""
  echo "  1. Go to: https://dashboard.render.com/select-repo"
  echo "  2. Connect your FinMind fork"
  echo "  3. Render will detect render.yaml automatically"
  echo "  4. Click 'Apply' to provision all services"
  echo ""
  echo "  Spec: deploy/platforms/render/render.yaml"
}

# ─── fly ─────────────────────────────────────────────────────────────────────
deploy_fly() {
  check_tool flyctl
  log "Deploying backend to Fly.io..."
  cd "$REPO_ROOT"
  flyctl deploy --config deploy/platforms/fly/fly-backend.toml
  log "Deploying frontend to Fly.io..."
  flyctl deploy --config deploy/platforms/fly/fly-frontend.toml
  ok "Fly.io deployment complete."
}

# ─── digitalocean ────────────────────────────────────────────────────────────
deploy_digitalocean() {
  check_tool doctl
  log "Creating DigitalOcean App..."
  doctl apps create --spec "$REPO_ROOT/deploy/platforms/digitalocean/app.yaml" --wait
  ok "DigitalOcean App Platform deployment complete."
}

# ─── netlify ─────────────────────────────────────────────────────────────────
deploy_netlify() {
  check_tool netlify
  log "Building and deploying frontend to Netlify..."
  cd "$REPO_ROOT/app"
  npm ci && npm run build
  netlify deploy --prod --dir dist
  ok "Netlify deployment complete."
}

# ─── vercel ──────────────────────────────────────────────────────────────────
deploy_vercel() {
  check_tool vercel
  log "Deploying frontend to Vercel..."
  cd "$REPO_ROOT/app"
  vercel --prod
  ok "Vercel deployment complete."
}

# ─── dispatch ────────────────────────────────────────────────────────────────
banner
case "$PLATFORM" in
  local)         deploy_local "$@" ;;
  k8s|kubernetes) deploy_k8s "$@" ;;
  helm)          deploy_helm "$@" ;;
  tilt)          deploy_tilt "$@" ;;
  aws)           deploy_aws "$@" ;;
  gcp)           deploy_gcp "$@" ;;
  azure)         deploy_azure "$@" ;;
  railway)       deploy_railway "$@" ;;
  render)        deploy_render "$@" ;;
  fly|flyio)     deploy_fly "$@" ;;
  do|digitalocean) deploy_digitalocean "$@" ;;
  netlify)       deploy_netlify "$@" ;;
  vercel)        deploy_vercel "$@" ;;
  *)
    echo "Unknown platform: $PLATFORM"
    echo "Available: local, k8s, helm, tilt, aws, gcp, azure, railway, render, fly, digitalocean, netlify, vercel"
    exit 1
    ;;
esac
