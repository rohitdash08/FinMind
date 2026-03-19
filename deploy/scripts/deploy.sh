#!/usr/bin/env bash
# FinMind Universal One-Click Deployment Script
# Usage: ./deploy/scripts/deploy.sh <platform>
#
# Supported platforms:
#   docker-compose  - Local Docker Compose (default)
#   kubernetes      - Kubernetes via Helm
#   tilt            - Local K8s dev with Tilt
#   railway         - Railway PaaS
#   heroku          - Heroku
#   digitalocean    - DigitalOcean App Platform
#   do-droplet      - DigitalOcean Droplet
#   render          - Render
#   flyio           - Fly.io
#   aws-ecs         - AWS ECS Fargate
#   aws-apprunner   - AWS App Runner
#   gcp             - Google Cloud Run
#   azure           - Azure Container Apps
#   netlify         - Netlify (frontend only)
#   vercel          - Vercel (frontend only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLATFORM="${1:-docker-compose}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Pre-flight checks
preflight_check() {
    log_info "Running pre-flight checks for: $PLATFORM"

    # Check .env exists
    if [ ! -f "$ROOT_DIR/.env" ] && [ "$PLATFORM" = "docker-compose" ]; then
        if [ -f "$ROOT_DIR/.env.example" ]; then
            log_warn ".env not found. Copying from .env.example..."
            cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
            log_warn "Please edit .env with your configuration before deploying to production."
        else
            log_error ".env.example not found"
            exit 1
        fi
    fi
}

# Smoke test after deployment
smoke_test() {
    local url="${1:?URL required}"
    local path="${2:-/health}"
    local max_retries=30
    local retry=0

    log_info "Running smoke test: $url$path"
    while [ $retry -lt $max_retries ]; do
        if curl -sf "$url$path" >/dev/null 2>&1; then
            log_ok "Smoke test passed: $url$path"
            return 0
        fi
        retry=$((retry + 1))
        sleep 2
    done
    log_error "Smoke test failed after $max_retries retries: $url$path"
    return 1
}

deploy_docker_compose() {
    log_info "Deploying with Docker Compose..."
    command -v docker >/dev/null 2>&1 || { log_error "Docker not found"; exit 1; }

    cd "$ROOT_DIR"
    preflight_check

    docker compose build
    docker compose up -d

    log_info "Waiting for services to start..."
    sleep 10

    smoke_test "http://localhost:8000" "/health" || true
    smoke_test "http://localhost:5173" "/" || true

    log_ok "Docker Compose deployment complete!"
    echo ""
    echo "  Frontend:   http://localhost:5173"
    echo "  Backend:    http://localhost:8000"
    echo "  Nginx:      http://localhost:8080"
    echo "  Grafana:    http://localhost:3000"
    echo "  Prometheus: http://localhost:9090"
}

deploy_kubernetes() {
    log_info "Deploying to Kubernetes with Helm..."
    command -v helm >/dev/null 2>&1 || { log_error "Helm not found. Install: https://helm.sh/docs/intro/install/"; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl not found"; exit 1; }

    cd "$ROOT_DIR"

    NAMESPACE="${K8S_NAMESPACE:-finmind}"
    RELEASE="${HELM_RELEASE:-finmind}"

    log_info "Installing Helm chart (namespace: $NAMESPACE, release: $RELEASE)..."
    helm upgrade --install "$RELEASE" deploy/helm/finmind \
        --namespace "$NAMESPACE" \
        --create-namespace \
        --set global.namespace="$NAMESPACE" \
        --wait --timeout 5m

    log_ok "Kubernetes deployment complete!"
    echo ""
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl get svc -n $NAMESPACE"
    echo "  kubectl port-forward -n $NAMESPACE svc/$RELEASE-backend 8000:8000"
    echo "  kubectl port-forward -n $NAMESPACE svc/$RELEASE-frontend 8080:80"
}

deploy_tilt() {
    log_info "Starting Tilt development environment..."
    command -v tilt >/dev/null 2>&1 || { log_error "Tilt not found. Install: https://docs.tilt.dev/install.html"; exit 1; }

    cd "$ROOT_DIR"
    tilt up
}

deploy_railway() {
    log_info "Deploying to Railway..."
    command -v railway >/dev/null 2>&1 || { log_error "Railway CLI not found. Install: npm install -g @railway/cli"; exit 1; }

    cd "$ROOT_DIR"
    log_info "Copy railway.toml to project root..."
    cp deploy/platforms/railway/railway.toml .
    railway up
    log_ok "Railway deployment initiated!"
}

deploy_heroku() {
    log_info "Deploying to Heroku..."
    command -v heroku >/dev/null 2>&1 || { log_error "Heroku CLI not found. Install: https://devcenter.heroku.com/articles/heroku-cli"; exit 1; }

    cd "$ROOT_DIR"
    HEROKU_APP="${HEROKU_APP:-finmind}"

    heroku container:login
    heroku container:push web --app "$HEROKU_APP" --context-path ./packages/backend
    heroku container:release web --app "$HEROKU_APP"
    heroku run "python -m flask --app wsgi:app init-db" --app "$HEROKU_APP"

    log_ok "Heroku deployment complete!"
    heroku open --app "$HEROKU_APP"
}

deploy_digitalocean() {
    log_info "Deploying to DigitalOcean App Platform..."
    command -v doctl >/dev/null 2>&1 || { log_error "doctl not found. Install: https://docs.digitalocean.com/reference/doctl/how-to/install/"; exit 1; }

    cd "$ROOT_DIR"
    doctl apps create --spec deploy/platforms/digitalocean/app-platform/do-app-spec.yaml
    log_ok "DigitalOcean App Platform deployment initiated!"
}

deploy_do_droplet() {
    log_info "Deploying to DigitalOcean Droplet..."
    bash "$ROOT_DIR/deploy/platforms/digitalocean/droplet/setup.sh"
}

deploy_render() {
    log_info "Deploying to Render..."
    log_info "Use the Render Blueprint: deploy/platforms/render/render.yaml"
    log_info "1. Go to https://dashboard.render.com"
    log_info "2. New > Blueprint Instance"
    log_info "3. Connect your GitHub repo"
    log_info "4. Render will auto-detect render.yaml"
    log_ok "Render blueprint ready at: deploy/platforms/render/render.yaml"
}

deploy_flyio() {
    log_info "Deploying to Fly.io..."
    command -v fly >/dev/null 2>&1 || { log_error "fly CLI not found. Install: https://fly.io/docs/hands-on/install-flyctl/"; exit 1; }

    cd "$ROOT_DIR"

    # Create Postgres + Redis
    log_info "Setting up Fly.io Postgres..."
    fly postgres create --name finmind-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1 || true

    log_info "Setting up Fly.io Redis..."
    fly redis create --name finmind-redis --region iad --no-replicas || true

    # Deploy backend
    log_info "Deploying backend..."
    fly deploy --config deploy/platforms/flyio/backend/fly.toml --app finmind-backend

    # Deploy frontend
    log_info "Deploying frontend..."
    fly deploy --config deploy/platforms/flyio/frontend/fly.toml --app finmind-frontend

    log_ok "Fly.io deployment complete!"
}

deploy_aws_ecs() {
    log_info "Deploying to AWS ECS Fargate..."
    bash "$ROOT_DIR/deploy/platforms/aws/ecs-fargate/deploy.sh"
}

deploy_aws_apprunner() {
    log_info "Deploying to AWS App Runner..."
    command -v aws >/dev/null 2>&1 || { log_error "AWS CLI not found"; exit 1; }
    log_info "Config: deploy/platforms/aws/app-runner/apprunner.yaml"
    log_info "Fill in environment variables and run:"
    echo "  aws apprunner create-service --cli-input-yaml file://deploy/platforms/aws/app-runner/apprunner.yaml"
}

deploy_gcp() {
    log_info "Deploying to GCP Cloud Run..."
    bash "$ROOT_DIR/deploy/platforms/gcp/deploy.sh"
}

deploy_azure() {
    log_info "Deploying to Azure Container Apps..."
    bash "$ROOT_DIR/deploy/platforms/azure/deploy.sh"
}

deploy_netlify() {
    log_info "Deploying frontend to Netlify..."
    command -v netlify >/dev/null 2>&1 || { log_error "Netlify CLI not found. Install: npm install -g netlify-cli"; exit 1; }

    cd "$ROOT_DIR"
    cp deploy/platforms/netlify/netlify.toml app/netlify.toml
    cd app
    npm ci && npm run build
    netlify deploy --prod --dir=dist
    log_ok "Netlify deployment complete!"
}

deploy_vercel() {
    log_info "Deploying frontend to Vercel..."
    command -v vercel >/dev/null 2>&1 || { log_error "Vercel CLI not found. Install: npm install -g vercel"; exit 1; }

    cd "$ROOT_DIR"
    cp deploy/platforms/vercel/vercel.json .
    vercel --prod
    log_ok "Vercel deployment complete!"
}

# Main dispatcher
echo "================================================"
echo "  FinMind Universal Deployment"
echo "  Platform: $PLATFORM"
echo "================================================"
echo ""

case "$PLATFORM" in
    docker-compose|docker|compose)  deploy_docker_compose ;;
    kubernetes|k8s|helm)            deploy_kubernetes ;;
    tilt|dev)                       deploy_tilt ;;
    railway)                        deploy_railway ;;
    heroku)                         deploy_heroku ;;
    digitalocean|do)                deploy_digitalocean ;;
    do-droplet|droplet)             deploy_do_droplet ;;
    render)                         deploy_render ;;
    flyio|fly)                      deploy_flyio ;;
    aws-ecs|ecs|fargate)            deploy_aws_ecs ;;
    aws-apprunner|apprunner)        deploy_aws_apprunner ;;
    gcp|cloudrun|cloud-run)         deploy_gcp ;;
    azure|aca|container-apps)       deploy_azure ;;
    netlify)                        deploy_netlify ;;
    vercel)                         deploy_vercel ;;
    *)
        log_error "Unknown platform: $PLATFORM"
        echo ""
        echo "Supported platforms:"
        echo "  docker-compose  - Local Docker Compose (default)"
        echo "  kubernetes      - Kubernetes via Helm"
        echo "  tilt            - Local K8s dev with Tilt"
        echo "  railway         - Railway PaaS"
        echo "  heroku          - Heroku"
        echo "  digitalocean    - DigitalOcean App Platform"
        echo "  do-droplet      - DigitalOcean Droplet"
        echo "  render          - Render"
        echo "  flyio           - Fly.io"
        echo "  aws-ecs         - AWS ECS Fargate"
        echo "  aws-apprunner   - AWS App Runner"
        echo "  gcp             - Google Cloud Run"
        echo "  azure           - Azure Container Apps"
        echo "  netlify         - Netlify (frontend only)"
        echo "  vercel          - Vercel (frontend only)"
        exit 1
        ;;
esac
