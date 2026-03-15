#!/usr/bin/env bash
# ============================================================================
# FinMind — Universal One-Click Deployment Script
# ============================================================================
#
# Usage:
#   ./deploy.sh <platform>            Deploy to the specified platform
#   ./deploy.sh --list                List all supported platforms
#   ./deploy.sh --help                Show this help
#
# Supported platforms:
#   docker        Docker Compose (local/VPS)
#   kubernetes    Raw Kubernetes manifests
#   helm          Helm chart (production K8s)
#   tilt          Tilt local K8s dev workflow
#   railway       Railway PaaS
#   heroku        Heroku (Docker)
#   render        Render Blueprint
#   fly           Fly.io
#   digitalocean  DigitalOcean App Platform
#   droplet       DigitalOcean Droplet (VPS)
#   aws           AWS ECS Fargate
#   gcp           GCP Cloud Run
#   azure         Azure Container Apps
#   netlify       Netlify (frontend only)
#   vercel        Vercel (frontend only)
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

check_env_file() {
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
            warn ".env not found — copying from .env.example"
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            warn "Please edit .env with your production values before deploying."
        else
            error "No .env file found. Create one from .env.example first."
            exit 1
        fi
    fi
}

require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        error "Required command '$1' not found. Please install it first."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Platform deployers
# ---------------------------------------------------------------------------

deploy_docker() {
    info "Deploying with Docker Compose..."
    require_cmd docker
    check_env_file

    docker compose up -d --build
    ok "FinMind is running!"
    echo "  Frontend: http://localhost:5173"
    echo "  Backend:  http://localhost:8000"
    echo "  Grafana:  http://localhost:3000"
}

deploy_kubernetes() {
    info "Deploying to Kubernetes (raw manifests)..."
    require_cmd kubectl
    check_env_file

    kubectl apply -f deploy/k8s/namespace.yaml
    kubectl apply -f deploy/k8s/secrets.example.yaml  # User should create real secrets
    kubectl apply -f deploy/k8s/app-stack.yaml
    kubectl apply -f deploy/k8s/monitoring-stack.yaml

    ok "FinMind deployed to Kubernetes!"
    echo "  kubectl get pods -n finmind"
    echo "  kubectl port-forward -n finmind svc/backend 8000:8000"
}

deploy_helm() {
    info "Deploying with Helm..."
    require_cmd helm
    require_cmd kubectl

    helm upgrade --install finmind deploy/helm/finmind \
        --namespace finmind \
        --create-namespace \
        --wait \
        --timeout 10m \
        "$@"

    ok "FinMind deployed via Helm!"
    echo "  helm status finmind -n finmind"
    echo "  kubectl get pods -n finmind"
}

deploy_tilt() {
    info "Starting Tilt local development..."
    require_cmd tilt
    require_cmd kubectl

    tilt up
}

deploy_railway() {
    info "Deploying to Railway..."
    require_cmd railway

    echo "1. Link this project to Railway:"
    echo "   railway link"
    echo ""
    echo "2. Deploy:"
    echo "   railway up"
    echo ""
    echo "3. Or use the Deploy button in the Railway dashboard:"
    echo "   https://railway.app/new"
    echo ""
    echo "Config: deploy/railway/railway.json"
}

deploy_heroku() {
    info "Deploying to Heroku..."
    require_cmd heroku

    echo "Option 1: Heroku Button (recommended)"
    echo "  Click: https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind"
    echo ""
    echo "Option 2: CLI"
    echo "  heroku create finmind-app"
    echo "  heroku addons:create heroku-postgresql:essential-0"
    echo "  heroku addons:create heroku-redis:mini"
    echo "  heroku stack:set container"
    echo "  git push heroku main"
    echo ""
    echo "Config: deploy/heroku/heroku.yml, deploy/heroku/app.json"
}

deploy_render() {
    info "Deploying to Render..."
    echo "Option 1: Render Blueprint (recommended)"
    echo "  1. Go to https://render.com/deploy"
    echo "  2. Connect your GitHub repo"
    echo "  3. Render will auto-detect deploy/render/render.yaml"
    echo ""
    echo "Option 2: Manual setup"
    echo "  Follow the spec in deploy/render/render.yaml"
}

deploy_fly() {
    info "Deploying to Fly.io..."
    require_cmd flyctl

    bash deploy/fly/deploy.sh "$@"
}

deploy_digitalocean() {
    info "Deploying to DigitalOcean App Platform..."
    require_cmd doctl

    echo "1. Create the app:"
    echo "   doctl apps create --spec deploy/digitalocean/app-spec.yaml"
    echo ""
    echo "2. Or use the DO dashboard:"
    echo "   Import deploy/digitalocean/app-spec.yaml"
}

deploy_droplet() {
    info "Deploying to DigitalOcean Droplet..."
    echo "1. Create an Ubuntu 22.04 droplet"
    echo "2. SSH in and run:"
    echo "   curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/droplet-setup.sh | bash"
    echo ""
    echo "Or copy and run deploy/digitalocean/droplet-setup.sh manually."
}

deploy_aws() {
    info "Deploying to AWS ECS Fargate..."
    require_cmd aws

    bash deploy/aws/deploy.sh "$@"
}

deploy_gcp() {
    info "Deploying to GCP Cloud Run..."
    require_cmd gcloud

    bash deploy/gcp/deploy.sh "$@"
}

deploy_azure() {
    info "Deploying to Azure Container Apps..."
    require_cmd az

    bash deploy/azure/deploy.sh "$@"
}

deploy_netlify() {
    info "Deploying frontend to Netlify..."
    require_cmd netlify

    echo "1. Connect repo to Netlify dashboard"
    echo "2. Set base directory: app"
    echo "3. Set build command: npm run build"
    echo "4. Set publish directory: app/dist"
    echo "5. Add env var: VITE_API_URL=https://your-backend-url"
    echo ""
    echo "Or use CLI:"
    echo "  cd app && netlify deploy --prod"
    echo ""
    echo "Config: deploy/netlify/netlify.toml"
}

deploy_vercel() {
    info "Deploying frontend to Vercel..."
    require_cmd vercel

    echo "1. Import project from GitHub in Vercel dashboard"
    echo "2. Set root directory: app"
    echo "3. Framework: Vite"
    echo "4. Add env var: VITE_API_URL=https://your-backend-url"
    echo ""
    echo "Or use CLI:"
    echo "  cd app && vercel --prod"
    echo ""
    echo "Config: deploy/vercel/vercel.json"
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

show_help() {
    echo "FinMind — Universal One-Click Deployment"
    echo ""
    echo "Usage: ./deploy.sh <platform> [options]"
    echo ""
    echo "Full-stack platforms:"
    echo "  docker          Docker Compose (local/VPS)"
    echo "  kubernetes      Raw Kubernetes manifests"
    echo "  helm            Helm chart (production K8s)"
    echo "  tilt            Tilt local K8s dev workflow"
    echo "  railway         Railway PaaS"
    echo "  heroku          Heroku (Docker)"
    echo "  render          Render Blueprint"
    echo "  fly             Fly.io"
    echo "  digitalocean    DigitalOcean App Platform"
    echo "  droplet         DigitalOcean Droplet (VPS)"
    echo "  aws             AWS ECS Fargate"
    echo "  gcp             GCP Cloud Run"
    echo "  azure           Azure Container Apps"
    echo ""
    echo "Frontend-only platforms:"
    echo "  netlify          Netlify"
    echo "  vercel           Vercel"
    echo ""
    echo "Options:"
    echo "  --list           List all platforms"
    echo "  --help           Show this help"
}

list_platforms() {
    echo "Supported platforms:"
    echo "  docker, kubernetes, helm, tilt"
    echo "  railway, heroku, render, fly"
    echo "  digitalocean, droplet, aws, gcp, azure"
    echo "  netlify, vercel"
}

case "${1:-}" in
    docker)         deploy_docker ;;
    kubernetes|k8s) deploy_kubernetes ;;
    helm)           shift; deploy_helm "$@" ;;
    tilt)           deploy_tilt ;;
    railway)        deploy_railway ;;
    heroku)         deploy_heroku ;;
    render)         deploy_render ;;
    fly)            shift; deploy_fly "$@" ;;
    digitalocean|do) deploy_digitalocean ;;
    droplet)        deploy_droplet ;;
    aws)            shift; deploy_aws "$@" ;;
    gcp)            shift; deploy_gcp "$@" ;;
    azure)          shift; deploy_azure "$@" ;;
    netlify)        deploy_netlify ;;
    vercel)         deploy_vercel ;;
    --list)         list_platforms ;;
    --help|-h|"")   show_help ;;
    *)
        error "Unknown platform: $1"
        echo "Run './deploy.sh --list' to see supported platforms."
        exit 1
        ;;
esac
