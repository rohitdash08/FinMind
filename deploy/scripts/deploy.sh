#!/usr/bin/env bash
# =============================================================================
# FinMind — Unified Deployment Script
# =============================================================================
# A single entry point for deploying FinMind to any supported platform.
#
# Usage:
#   ./deploy/scripts/deploy.sh --platform <platform> [options]
#
# Platforms:
#   docker            Docker Compose (production)
#   kubernetes        Kubernetes via Helm
#   railway           Railway
#   render            Render
#   fly               Fly.io
#   heroku            Heroku
#   digitalocean      DigitalOcean App Platform
#   aws-ecs           AWS ECS Fargate
#   aws-apprunner     AWS App Runner
#   gcp-cloudrun      GCP Cloud Run
#   azure             Azure Container Apps
#   netlify           Netlify (frontend only)
#   vercel            Vercel (frontend only)
#
# Options:
#   --env <file>      Path to .env file (default: .env)
#   --tag <tag>       Docker image tag (default: latest)
#   --dry-run         Print commands without executing
#   --help            Show this help message
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PLATFORM=""
ENV_FILE="${REPO_ROOT}/.env"
IMAGE_TAG="latest"
DRY_RUN=false

# ---------------------------------------------------------------------------
# Colors for output
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $*"
    else
        log_info "Running: $*"
        eval "$@"
    fi
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        log_error "'$1' is not installed. Please install it first."
        exit 1
    fi
}

usage() {
    head -35 "$0" | tail -30
    exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform)  PLATFORM="$2";   shift 2 ;;
        --env)       ENV_FILE="$2";   shift 2 ;;
        --tag)       IMAGE_TAG="$2";  shift 2 ;;
        --dry-run)   DRY_RUN=true;    shift   ;;
        --help|-h)   usage ;;
        *)           log_error "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$PLATFORM" ]; then
    log_error "Platform is required. Use --platform <platform>"
    usage
fi

# ---------------------------------------------------------------------------
# Load environment file if it exists
# ---------------------------------------------------------------------------
if [ -f "$ENV_FILE" ]; then
    log_info "Loading environment from ${ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    log_warn "No .env file found at ${ENV_FILE}. Using environment variables."
fi

# ---------------------------------------------------------------------------
# Platform: Docker Compose
# ---------------------------------------------------------------------------
deploy_docker() {
    log_info "Deploying FinMind with Docker Compose (production)"
    check_command docker

    run_cmd "docker compose -f ${DEPLOY_DIR}/docker/docker-compose.prod.yml \
        --env-file ${ENV_FILE} \
        build --no-cache"

    run_cmd "docker compose -f ${DEPLOY_DIR}/docker/docker-compose.prod.yml \
        --env-file ${ENV_FILE} \
        up -d"

    log_ok "Docker Compose deployment complete."
    log_info "Frontend: http://localhost:${LISTEN_PORT:-80}"
    log_info "Health:   http://localhost:${LISTEN_PORT:-80}/health"
}

# ---------------------------------------------------------------------------
# Platform: Kubernetes (Helm)
# ---------------------------------------------------------------------------
deploy_kubernetes() {
    log_info "Deploying FinMind to Kubernetes via Helm"
    check_command helm
    check_command kubectl

    local HELM_ARGS=(
        "upgrade" "--install" "finmind"
        "${DEPLOY_DIR}/helm/finmind"
        "--namespace" "finmind"
        "--create-namespace"
        "--set" "backend.image.tag=${IMAGE_TAG}"
        "--set" "frontend.image.tag=${IMAGE_TAG}"
    )

    # Pass secrets via --set if environment variables are available
    [ -n "${POSTGRES_PASSWORD:-}" ] && HELM_ARGS+=("--set" "secrets.POSTGRES_PASSWORD=${POSTGRES_PASSWORD}")
    [ -n "${JWT_SECRET:-}" ]        && HELM_ARGS+=("--set" "secrets.JWT_SECRET=${JWT_SECRET}")
    [ -n "${GEMINI_API_KEY:-}" ]    && HELM_ARGS+=("--set" "secrets.GEMINI_API_KEY=${GEMINI_API_KEY}")

    run_cmd "helm ${HELM_ARGS[*]}"
    log_ok "Helm deployment complete. Run 'kubectl get pods -n finmind' to check status."
}

# ---------------------------------------------------------------------------
# Platform: Railway
# ---------------------------------------------------------------------------
deploy_railway() {
    log_info "Deploying FinMind to Railway"
    check_command railway

    run_cmd "cd ${REPO_ROOT} && railway up --config ${DEPLOY_DIR}/platforms/railway/railway.toml"
    log_ok "Railway deployment triggered."
}

# ---------------------------------------------------------------------------
# Platform: Render
# ---------------------------------------------------------------------------
deploy_render() {
    log_info "Deploying FinMind to Render"
    log_info "Render deployments are triggered via the dashboard blueprint."
    log_info "Blueprint file: ${DEPLOY_DIR}/platforms/render/render.yaml"
    log_info ""
    log_info "Steps:"
    log_info "  1. Push this repo to GitHub"
    log_info "  2. Go to https://dashboard.render.com/blueprints"
    log_info "  3. Click 'New Blueprint Instance'"
    log_info "  4. Connect your GitHub repo"
    log_info "  5. Render will auto-detect render.yaml"
    log_ok "Render config ready."
}

# ---------------------------------------------------------------------------
# Platform: Fly.io
# ---------------------------------------------------------------------------
deploy_fly() {
    log_info "Deploying FinMind to Fly.io"
    check_command fly

    # Backend
    log_info "Deploying backend..."
    run_cmd "cd ${REPO_ROOT} && fly deploy --config ${DEPLOY_DIR}/platforms/fly/fly.toml"

    # Frontend
    log_info "Deploying frontend..."
    run_cmd "cd ${REPO_ROOT} && fly deploy --config ${DEPLOY_DIR}/platforms/fly/fly-frontend.toml"

    log_ok "Fly.io deployment complete."
}

# ---------------------------------------------------------------------------
# Platform: Heroku
# ---------------------------------------------------------------------------
deploy_heroku() {
    log_info "Deploying FinMind to Heroku"
    check_command heroku

    log_info "Deploying backend via container..."
    run_cmd "cd ${REPO_ROOT} && heroku container:push web \
        --app finmind-backend \
        --dockerfile ${DEPLOY_DIR}/docker/backend.Dockerfile"
    run_cmd "heroku container:release web --app finmind-backend"

    log_ok "Heroku deployment complete."
}

# ---------------------------------------------------------------------------
# Platform: DigitalOcean App Platform
# ---------------------------------------------------------------------------
deploy_digitalocean() {
    log_info "Deploying FinMind to DigitalOcean App Platform"
    check_command doctl

    run_cmd "doctl apps create --spec ${DEPLOY_DIR}/platforms/digitalocean/.do/app.yaml"
    log_ok "DigitalOcean deployment triggered."
}

# ---------------------------------------------------------------------------
# Platform: AWS ECS Fargate
# ---------------------------------------------------------------------------
deploy_aws_ecs() {
    log_info "Deploying FinMind to AWS ECS Fargate"
    check_command aws
    check_command docker

    local ACCOUNT_ID
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    local ECR_REPO="${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-backend"

    log_info "Building and pushing Docker image to ECR..."
    run_cmd "aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ECR_REPO}"
    run_cmd "docker build -f ${DEPLOY_DIR}/docker/backend.Dockerfile -t finmind-backend:${IMAGE_TAG} ${REPO_ROOT}"
    run_cmd "docker tag finmind-backend:${IMAGE_TAG} ${ECR_REPO}:${IMAGE_TAG}"
    run_cmd "docker push ${ECR_REPO}:${IMAGE_TAG}"

    log_info "Updating ECS service..."
    run_cmd "aws ecs update-service --cluster finmind --service finmind-backend --force-new-deployment"
    log_ok "AWS ECS deployment triggered."
}

# ---------------------------------------------------------------------------
# Platform: AWS App Runner
# ---------------------------------------------------------------------------
deploy_aws_apprunner() {
    log_info "Deploying FinMind to AWS App Runner"
    check_command aws

    log_info "See ${DEPLOY_DIR}/platforms/aws/apprunner.yaml for configuration."
    log_info "Use: aws apprunner create-service --cli-input-yaml file://${DEPLOY_DIR}/platforms/aws/apprunner.yaml"
    log_ok "AWS App Runner config ready."
}

# ---------------------------------------------------------------------------
# Platform: GCP Cloud Run
# ---------------------------------------------------------------------------
deploy_gcp_cloudrun() {
    log_info "Deploying FinMind to Google Cloud Run"
    check_command gcloud

    local PROJECT_ID
    PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

    log_info "Building image with Cloud Build..."
    run_cmd "cd ${REPO_ROOT} && gcloud builds submit \
        --tag gcr.io/${PROJECT_ID}/finmind-backend:${IMAGE_TAG} \
        --timeout=600 ."

    log_info "Deploying to Cloud Run..."
    run_cmd "gcloud run deploy finmind-backend \
        --image gcr.io/${PROJECT_ID}/finmind-backend:${IMAGE_TAG} \
        --region us-central1 \
        --platform managed \
        --port 8000 \
        --memory 512Mi \
        --cpu 1 \
        --min-instances 1 \
        --max-instances 10 \
        --allow-unauthenticated"

    log_ok "GCP Cloud Run deployment complete."
}

# ---------------------------------------------------------------------------
# Platform: Azure Container Apps
# ---------------------------------------------------------------------------
deploy_azure() {
    log_info "Deploying FinMind to Azure Container Apps"
    check_command az

    log_info "See ${DEPLOY_DIR}/platforms/azure/containerapp.yaml for configuration."
    run_cmd "az containerapp update \
        --name finmind-backend \
        --resource-group finmind-rg \
        --yaml ${DEPLOY_DIR}/platforms/azure/containerapp.yaml"

    log_ok "Azure Container Apps deployment complete."
}

# ---------------------------------------------------------------------------
# Platform: Netlify (frontend only)
# ---------------------------------------------------------------------------
deploy_netlify() {
    log_info "Deploying FinMind frontend to Netlify"
    check_command netlify

    run_cmd "cd ${REPO_ROOT}/app && npm ci && npm run build"
    run_cmd "netlify deploy --prod --dir=${REPO_ROOT}/app/dist"
    log_ok "Netlify deployment complete."
}

# ---------------------------------------------------------------------------
# Platform: Vercel (frontend only)
# ---------------------------------------------------------------------------
deploy_vercel() {
    log_info "Deploying FinMind frontend to Vercel"
    check_command vercel

    run_cmd "cd ${REPO_ROOT}/app && vercel --prod"
    log_ok "Vercel deployment complete."
}

# ---------------------------------------------------------------------------
# Dispatch to platform handler
# ---------------------------------------------------------------------------
case "$PLATFORM" in
    docker)          deploy_docker ;;
    kubernetes|k8s)  deploy_kubernetes ;;
    railway)         deploy_railway ;;
    render)          deploy_render ;;
    fly)             deploy_fly ;;
    heroku)          deploy_heroku ;;
    digitalocean)    deploy_digitalocean ;;
    aws-ecs)         deploy_aws_ecs ;;
    aws-apprunner)   deploy_aws_apprunner ;;
    gcp-cloudrun)    deploy_gcp_cloudrun ;;
    azure)           deploy_azure ;;
    netlify)         deploy_netlify ;;
    vercel)          deploy_vercel ;;
    *)
        log_error "Unknown platform: ${PLATFORM}"
        usage
        ;;
esac
