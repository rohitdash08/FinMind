#!/bin/bash
set -euo pipefail

# FinMind Universal One-Click Deploy Script
# Usage: bash deploy/deploy.sh [platform]
# Platforms: docker, k8s, helm, tilt, railway, heroku, render, flyio,
#            digitalocean-app, digitalocean-droplet, aws-ecs, aws-apprunner,
#            gcp-cloudrun, azure-container-apps

PLATFORM="${1:-docker}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
NC='[0m'

log()   { echo -e "${GREEN}[FinMind]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

check_deps() {
    for cmd in "$@"; do
        command -v "$cmd" &>/dev/null || error "$cmd is required but not installed."
    done
}

setup_env() {
    if [ ! -f "$ROOT_DIR/.env" ]; then
        log "Creating .env from .env.example..."
        cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
        if command -v openssl &>/dev/null; then
            sed -i "s/JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" "$ROOT_DIR/.env"
            sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" "$ROOT_DIR/.env"
        fi
        warn "Please review .env and update values before production use."
    fi
}

deploy_docker() {
    log "Deploying with Docker Compose..."
    check_deps docker
    setup_env
    cd "$ROOT_DIR"
    docker compose up -d --build
    log "Services starting..."
    log "Frontend: http://localhost:5173"
    log "Backend:  http://localhost:8000/health"
    log "Grafana:  http://localhost:3000"
}

deploy_docker_prod() {
    log "Deploying with Production Docker Compose..."
    check_deps docker
    setup_env
    cd "$ROOT_DIR"
    docker compose -f docker-compose.prod.yml up -d --build
    log "Production services starting..."
    log "App: http://localhost (port 80)"
}

deploy_helm() {
    log "Deploying with Helm to Kubernetes..."
    check_deps helm kubectl
    cd "$ROOT_DIR"
    helm upgrade --install finmind deploy/helm/finmind \
        --namespace finmind \
        --create-namespace \
        --wait --timeout 5m
    log "Helm deployment complete!"
    kubectl get pods -n finmind
}

deploy_tilt() {
    log "Starting Tilt development environment..."
    check_deps tilt kubectl
    cd "$ROOT_DIR"
    tilt up
}

deploy_railway() {
    log "Deploying to Railway..."
    check_deps railway
    cd "$ROOT_DIR"
    railway up
    log "Railway deployment initiated!"
}

deploy_heroku() {
    log "Deploying to Heroku..."
    check_deps heroku git
    cd "$ROOT_DIR"
    heroku container:push web --recursive
    heroku container:release web
    heroku run python -m flask --app wsgi:app init-db
    log "Heroku deployment complete!"
}

deploy_flyio() {
    log "Deploying to Fly.io..."
    check_deps fly
    cd "$ROOT_DIR"
    fly deploy --config deploy/platforms/flyio/fly.toml
    log "Fly.io backend deployment complete!"
}

deploy_render() {
    log "Deploying to Render..."
    log "Render uses render.yaml for Blueprint deployments."
    log "Visit: https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind"
}

deploy_gcp() {
    log "Deploying to GCP Cloud Run..."
    check_deps gcloud docker
    cd "$ROOT_DIR"
    gcloud builds submit --config deploy/platforms/gcp-cloudrun/cloudbuild.yaml
    log "GCP Cloud Run deployment complete!"
}

deploy_azure() {
    log "Deploying to Azure Container Apps..."
    check_deps az
    cd "$ROOT_DIR"
    bash deploy/platforms/azure-container-apps/deploy.sh
}

deploy_aws_ecs() {
    log "Deploying to AWS ECS Fargate..."
    check_deps aws
    cd "$ROOT_DIR"
    bash deploy/platforms/aws-ecs/deploy.sh
}

deploy_do_app() {
    log "Deploying to DigitalOcean App Platform..."
    check_deps doctl
    doctl apps create --spec deploy/platforms/digitalocean-app/app.yaml
    log "DigitalOcean App Platform deployment initiated!"
}

deploy_do_droplet() {
    log "Running DigitalOcean Droplet setup..."
    bash "$SCRIPT_DIR/platforms/digitalocean-droplet/setup.sh"
}

# Main
case "$PLATFORM" in
    docker)              deploy_docker ;;
    docker-prod|prod)    deploy_docker_prod ;;
    helm|k8s)            deploy_helm ;;
    tilt)                deploy_tilt ;;
    railway)             deploy_railway ;;
    heroku)              deploy_heroku ;;
    flyio|fly)           deploy_flyio ;;
    render)              deploy_render ;;
    gcp|gcp-cloudrun)    deploy_gcp ;;
    azure)               deploy_azure ;;
    aws-ecs|aws)         deploy_aws_ecs ;;
    digitalocean-app)    deploy_do_app ;;
    digitalocean-droplet) deploy_do_droplet ;;
    *)
        echo "Usage: bash deploy/deploy.sh [platform]"
        echo ""
        echo "Available platforms:"
        echo "  docker              - Local Docker Compose (development)"
        echo "  docker-prod         - Production Docker Compose"
        echo "  helm / k8s          - Kubernetes via Helm charts"
        echo "  tilt                - Local K8s dev with Tilt"
        echo "  railway             - Railway"
        echo "  heroku              - Heroku"
        echo "  flyio               - Fly.io"
        echo "  render              - Render"
        echo "  gcp-cloudrun        - Google Cloud Run"
        echo "  azure               - Azure Container Apps"
        echo "  aws-ecs             - AWS ECS Fargate"
        echo "  digitalocean-app    - DigitalOcean App Platform"
        echo "  digitalocean-droplet - DigitalOcean Droplet"
        exit 1
        ;;
esac
