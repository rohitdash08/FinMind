#!/usr/bin/env bash
# =============================================================================
# FinMind — Universal One-Click Deployment Script
# =============================================================================
# Usage:
#   ./scripts/deploy.sh [platform] [options]
#
# Platforms:
#   docker        Local Docker Compose (default)
#   k8s           Kubernetes with raw manifests
#   helm          Kubernetes with Helm chart
#   tilt          Local K8s dev with Tilt hot-reload
#   railway       Railway.app
#   render        Render.com
#   fly           Fly.io
#   heroku        Heroku
#   digitalocean  DigitalOcean App Platform
#   aws           AWS ECS/Fargate
#   gcp           Google Cloud Run
#   azure         Azure Container Apps
#   netlify       Netlify (frontend only)
#   vercel        Vercel (frontend only)
#
# Options:
#   --env ENV     Target environment (dev|staging|prod) [default: prod]
#   --tag TAG     Docker image tag [default: latest]
#   --dry-run     Print commands without executing
#   --help        Show this help
#
# Examples:
#   ./scripts/deploy.sh docker
#   ./scripts/deploy.sh helm --env prod --tag v1.2.3
#   ./scripts/deploy.sh fly --dry-run
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

log()  { echo -e "${BLUE}[finmind]${RESET} $*"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
die()  { echo -e "${RED}[✗]${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PLATFORM="${1:-docker}"
ENV="prod"
TAG="latest"
DRY_RUN=false
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
shift 1 2>/dev/null || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENV="$2";    shift 2 ;;
    --tag)      TAG="$2";    shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --help|-h)  sed -n '3,40p' "$0"; exit 0 ;;
    *)          die "Unknown option: $1. Run with --help for usage." ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run() {
  if $DRY_RUN; then
    echo -e "${YELLOW}[dry-run]${RESET} $*"
  else
    eval "$*"
  fi
}

require() {
  for cmd in "$@"; do
    command -v "$cmd" &>/dev/null || die "'$cmd' is required but not installed."
  done
}

check_env_var() {
  local var="$1"
  [[ -n "${!var:-}" ]] || die "Environment variable '$var' is not set."
}

banner() {
  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}║   FinMind Deployment — ${PLATFORM^^} / ${ENV^^}$(printf '%*s' $((18 - ${#PLATFORM} - ${#ENV})) '')║${RESET}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
  echo ""
}

# ---------------------------------------------------------------------------
# Platform handlers
# ---------------------------------------------------------------------------

deploy_docker() {
  require docker
  log "Starting Docker Compose stack (env=$ENV, tag=$TAG)..."
  cd "$REPO_ROOT"

  if [[ "$ENV" == "dev" ]]; then
    run "BACKEND_TAG=$TAG FRONTEND_TAG=$TAG docker compose up --build -d"
  else
    run "BACKEND_TAG=$TAG FRONTEND_TAG=$TAG docker compose up -d --pull always"
  fi

  ok "Docker stack is up. Services:"
  run "docker compose ps"
  echo ""
  echo "  API:      http://localhost:8080"
  echo "  Frontend: http://localhost:5173"
  echo "  Grafana:  http://localhost:3000"
}

deploy_k8s() {
  require kubectl
  log "Deploying to Kubernetes with raw manifests..."
  cd "$REPO_ROOT/deploy/k8s"

  run "kubectl apply -f namespace.yaml"
  run "kubectl apply -f secrets.example.yaml -n finmind" && \
    warn "Applied example secrets — update them with real values immediately!"
  run "kubectl apply -f app-stack.yaml -n finmind"
  run "kubectl apply -f monitoring-stack.yaml -n finmind"
  run "kubectl rollout status deployment/backend -n finmind --timeout=120s"

  ok "Kubernetes manifests applied."
}

deploy_helm() {
  require helm kubectl
  log "Deploying to Kubernetes with Helm (tag=$TAG)..."
  cd "$REPO_ROOT"

  run "kubectl apply -f deploy/k8s/namespace.yaml"
  run "helm upgrade --install finmind deploy/k8s/helm \
    --namespace finmind \
    --set backend.image.tag=$TAG \
    --set frontend.image.tag=$TAG \
    --atomic \
    --timeout 5m \
    --wait"

  ok "Helm release 'finmind' deployed."
  run "helm status finmind -n finmind"
}

deploy_tilt() {
  require tilt
  log "Starting Tilt local K8s dev environment..."
  cd "$REPO_ROOT/deploy/tilt"
  run "tilt up"
}

deploy_railway() {
  require railway
  log "Deploying to Railway..."
  cd "$REPO_ROOT"
  run "railway up --config deploy/platforms/railway/railway.toml"
  ok "Railway deployment triggered."
}

deploy_render() {
  log "Deploying to Render..."
  warn "Render deploys automatically on git push when connected to GitHub."
  warn "For manual deploy: https://dashboard.render.com → Manual Deploy"
  echo ""
  echo "  Blueprint spec: deploy/platforms/render/render.yaml"
  echo "  Import URL:     https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind"
}

deploy_fly() {
  require flyctl
  log "Deploying to Fly.io (tag=$TAG)..."
  cd "$REPO_ROOT"

  # Ensure secrets are set
  warn "Ensure these secrets are set: fly secrets set DATABASE_URL=... REDIS_URL=... JWT_SECRET=... GEMINI_API_KEY=..."

  run "flyctl deploy \
    --config deploy/platforms/fly/fly.toml \
    --image ghcr.io/rohitdash08/finmind-backend:$TAG \
    --remote-only"

  ok "Fly.io deployment complete."
  run "flyctl status --config deploy/platforms/fly/fly.toml"
}

deploy_heroku() {
  require heroku git
  log "Deploying to Heroku..."
  cd "$REPO_ROOT"

  APP_NAME="${HEROKU_APP_NAME:-finmind}"
  run "heroku stack:set container -a $APP_NAME"
  run "heroku config:set LOG_LEVEL=INFO GEMINI_MODEL=gemini-1.5-flash -a $APP_NAME"
  warn "Set secrets: heroku config:set JWT_SECRET=... GEMINI_API_KEY=... -a $APP_NAME"
  run "git push heroku main"

  ok "Heroku deployment pushed."
}

deploy_digitalocean() {
  require doctl
  log "Deploying to DigitalOcean App Platform..."
  cd "$REPO_ROOT"

  if doctl apps list --format ID,Spec.Name --no-header 2>/dev/null | grep -q finmind; then
    APP_ID=$(doctl apps list --format ID,Spec.Name --no-header | grep finmind | awk '{print $1}')
    run "doctl apps update $APP_ID --spec deploy/platforms/digitalocean/app.yaml"
    ok "DigitalOcean app updated: $APP_ID"
  else
    run "doctl apps create --spec deploy/platforms/digitalocean/app.yaml"
    ok "DigitalOcean app created."
  fi
}

deploy_aws() {
  require aws
  log "Deploying to AWS ECS/Fargate..."
  cd "$REPO_ROOT"

  CLUSTER="${AWS_ECS_CLUSTER:-finmind}"
  SERVICE="${AWS_ECS_SERVICE:-finmind-backend}"
  REGION="${AWS_REGION:-us-east-1}"

  # Register updated task definition
  TASK_DEF_ARN=$(run "aws ecs register-task-definition \
    --cli-input-json file://deploy/platforms/aws/task-definition.json \
    --region $REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text")

  # Update service to use new task definition
  run "aws ecs update-service \
    --cluster $CLUSTER \
    --service $SERVICE \
    --task-definition $TASK_DEF_ARN \
    --force-new-deployment \
    --region $REGION"

  ok "ECS service update triggered."
  log "Waiting for service stability..."
  run "aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --region $REGION"
  ok "ECS service is stable."
}

deploy_gcp() {
  require gcloud
  log "Deploying to Google Cloud Run..."
  cd "$REPO_ROOT"

  PROJECT="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
  REGION="${GCP_REGION:-us-east1}"

  # Replace placeholder PROJECT_ID
  TMP_FILE=$(mktemp)
  sed "s/PROJECT_ID/$PROJECT/g; s/REGION/$REGION/g" \
    deploy/platforms/gcp/cloudrun-service.yaml > "$TMP_FILE"

  run "gcloud run services replace $TMP_FILE --region $REGION --project $PROJECT"
  rm -f "$TMP_FILE"

  ok "Cloud Run services updated."
  run "gcloud run services list --region $REGION --project $PROJECT"
}

deploy_azure() {
  require az
  log "Deploying to Azure Container Apps..."
  cd "$REPO_ROOT"

  RG="${AZURE_RESOURCE_GROUP:-finmind-rg}"
  ENV_NAME="${AZURE_ENV:-finmind-env}"
  SUB="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"

  # Ensure environment exists
  run "az containerapp env show -n $ENV_NAME -g $RG &>/dev/null || \
    az containerapp env create -n $ENV_NAME -g $RG --location eastus"

  # Replace placeholder SUBSCRIPTION_ID
  TMP_FILE=$(mktemp)
  sed "s/SUBSCRIPTION_ID/$SUB/g" \
    deploy/platforms/azure/containerapps.yaml > "$TMP_FILE"

  run "az containerapp create \
    --yaml $TMP_FILE \
    --resource-group $RG \
    --subscription $SUB"

  rm -f "$TMP_FILE"
  ok "Azure Container Apps deployed."
}

deploy_netlify() {
  require netlify
  log "Deploying frontend to Netlify..."
  cd "$REPO_ROOT/app"

  run "npm ci && npm run build"
  run "netlify deploy --prod --dir dist --config ../deploy/platforms/netlify/netlify.toml"

  ok "Netlify deployment complete."
}

deploy_vercel() {
  require vercel
  log "Deploying frontend to Vercel..."
  cd "$REPO_ROOT/app"

  run "npm ci && npm run build"
  if [[ "$ENV" == "prod" ]]; then
    run "vercel --prod --yes"
  else
    run "vercel --yes"
  fi

  ok "Vercel deployment complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
banner

log "Platform: ${BOLD}$PLATFORM${RESET}  |  Env: ${BOLD}$ENV${RESET}  |  Tag: ${BOLD}$TAG${RESET}  |  Dry-run: ${BOLD}$DRY_RUN${RESET}"
echo ""

case "$PLATFORM" in
  docker)       deploy_docker ;;
  k8s)          deploy_k8s ;;
  helm)         deploy_helm ;;
  tilt)         deploy_tilt ;;
  railway)      deploy_railway ;;
  render)       deploy_render ;;
  fly)          deploy_fly ;;
  heroku)       deploy_heroku ;;
  digitalocean) deploy_digitalocean ;;
  aws)          deploy_aws ;;
  gcp)          deploy_gcp ;;
  azure)        deploy_azure ;;
  netlify)      deploy_netlify ;;
  vercel)       deploy_vercel ;;
  *)
    die "Unknown platform '$PLATFORM'.
Run: ./scripts/deploy.sh --help for a list of supported platforms."
    ;;
esac

echo ""
ok "Done! FinMind deployed to ${PLATFORM}."
