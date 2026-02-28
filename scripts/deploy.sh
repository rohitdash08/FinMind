#!/bin/bash
# FinMind Universal One-Click Deployment Script
# Usage: ./scripts/deploy.sh [platform] [environment]
#
# Platforms: docker, docker-prod, kubernetes, helm, tilt, fly, railway, render, heroku
# Environment: dev, staging, production (default: dev)

set -e

PLATFORM="${1:-docker}"
ENVIRONMENT="${2:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${BLUE}[FinMind]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check prerequisites
check_prereqs() {
    log "Checking prerequisites..."
    
    case "$PLATFORM" in
        docker|docker-prod)
            command -v docker >/dev/null 2>&1 || error "Docker is required"
            command -v docker compose >/dev/null 2>&1 || error "Docker Compose V2 is required"
            ;;
        kubernetes|helm)
            command -v kubectl >/dev/null 2>&1 || error "kubectl is required"
            command -v helm >/dev/null 2>&1 || error "Helm is required"
            ;;
        tilt)
            command -v tilt >/dev/null 2>&1 || error "Tilt is required (install from https://tilt.dev)"
            command -v kubectl >/dev/null 2>&1 || error "kubectl is required"
            ;;
        fly)
            command -v flyctl >/dev/null 2>&1 || error "flyctl is required (install from https://fly.io/docs/flyctl/install)"
            ;;
        railway)
            command -v railway >/dev/null 2>&1 || error "Railway CLI is required (npm install -g @railway/cli)"
            ;;
    esac
    
    success "Prerequisites check passed"
}

# Setup environment
setup_env() {
    log "Setting up environment..."
    
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            warn "Created .env from .env.example - please update with your secrets"
        fi
    fi
    
    # Generate JWT secret if not set
    if ! grep -q "JWT_SECRET=." "$PROJECT_ROOT/.env" 2>/dev/null; then
        JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | base64 | tr -d '\n' | head -c 64)
        echo "JWT_SECRET=$JWT_SECRET" >> "$PROJECT_ROOT/.env"
        success "Generated JWT_SECRET"
    fi
}

# Deploy with Docker Compose (dev)
deploy_docker() {
    log "Deploying with Docker Compose (development)..."
    cd "$PROJECT_ROOT"
    
    docker compose build
    docker compose up -d
    
    success "Docker Compose deployment complete!"
    echo ""
    log "Services running:"
    echo "  Frontend:   http://localhost:5173"
    echo "  Backend:    http://localhost:8000"
    echo "  Nginx:      http://localhost:8080"
    echo "  Grafana:    http://localhost:3000"
    echo "  Prometheus: http://localhost:9090"
    echo ""
    log "View logs: docker compose logs -f"
    log "Stop: docker compose down"
}

# Deploy with Docker Compose (production)
deploy_docker_prod() {
    log "Deploying with Docker Compose (production)..."
    cd "$PROJECT_ROOT"
    
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d
    
    success "Production Docker Compose deployment complete!"
    echo ""
    log "Services running:"
    echo "  Backend: http://localhost:8000"
    echo "  Nginx:   http://localhost:80"
    echo ""
    log "View logs: docker compose -f docker-compose.prod.yml logs -f"
    log "Stop: docker compose -f docker-compose.prod.yml down"
}

# Deploy with Kubernetes (raw manifests)
deploy_kubernetes() {
    log "Deploying to Kubernetes..."
    cd "$PROJECT_ROOT"
    
    # Create namespace
    kubectl apply -f deploy/k8s/namespace.yaml
    
    # Setup secrets
    if [ ! -f deploy/k8s/secrets.yaml ]; then
        cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
        warn "Created secrets.yaml from example - please update with your secrets before running again"
        warn "Edit: deploy/k8s/secrets.yaml"
        exit 1
    fi
    
    kubectl apply -f deploy/k8s/secrets.yaml
    kubectl apply -f deploy/k8s/app-stack.yaml
    
    # Wait for pods
    log "Waiting for pods to be ready..."
    kubectl wait --namespace finmind --for=condition=ready pod -l app=backend --timeout=300s || true
    
    success "Kubernetes deployment complete!"
    echo ""
    log "Check status: kubectl get pods -n finmind"
    log "Port forward backend: kubectl port-forward -n finmind svc/backend 8000:8000"
    log "Port forward nginx: kubectl port-forward -n finmind svc/nginx 8080:80"
}

# Deploy with Helm
deploy_helm() {
    log "Deploying with Helm..."
    cd "$PROJECT_ROOT/deploy/helm/finmind"
    
    # Add Bitnami repo for PostgreSQL and Redis
    helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    helm repo update
    
    # Update dependencies
    helm dependency update
    
    # Generate secrets if not provided
    JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 16)}"
    
    # Install/upgrade
    helm upgrade --install finmind . \
        --namespace finmind --create-namespace \
        --set secrets.jwtSecret="$JWT_SECRET" \
        --set postgresql.auth.password="$POSTGRES_PASSWORD" \
        --wait --timeout 10m
    
    success "Helm deployment complete!"
    echo ""
    log "Check status: helm status finmind -n finmind"
    log "Get pods: kubectl get pods -n finmind"
    log "Uninstall: helm uninstall finmind -n finmind"
}

# Deploy with Tilt (local K8s dev)
deploy_tilt() {
    log "Starting Tilt (local Kubernetes development)..."
    cd "$PROJECT_ROOT"
    
    # Setup secrets
    if [ ! -f deploy/k8s/secrets.yaml ]; then
        cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
        warn "Created secrets.yaml from example - please update with your secrets"
    fi
    
    tilt up
}

# Deploy to Fly.io
deploy_fly() {
    log "Deploying to Fly.io..."
    cd "$PROJECT_ROOT"
    
    # Check if app exists, create if not
    if ! flyctl apps list | grep -q "finmind-api"; then
        flyctl apps create finmind-api --org personal || true
        
        # Create managed PostgreSQL
        flyctl postgres create --name finmind-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x || true
        flyctl postgres attach finmind-db --app finmind-api || true
        
        # Create Redis
        flyctl redis create --name finmind-redis --region iad --no-replicas || true
    fi
    
    # Set secrets
    [ -n "$JWT_SECRET" ] && flyctl secrets set JWT_SECRET="$JWT_SECRET" --app finmind-api || true
    [ -n "$GEMINI_API_KEY" ] && flyctl secrets set GEMINI_API_KEY="$GEMINI_API_KEY" --app finmind-api || true
    
    # Deploy
    flyctl deploy --config deploy/fly/fly.toml --remote-only
    
    success "Fly.io deployment complete!"
    echo ""
    log "App URL: https://finmind-api.fly.dev"
    log "Logs: flyctl logs --app finmind-api"
    log "Dashboard: flyctl dashboard --app finmind-api"
}

# Deploy to Railway
deploy_railway() {
    log "Deploying to Railway..."
    cd "$PROJECT_ROOT"
    
    # Link project if not linked
    railway link 2>/dev/null || railway init
    
    # Deploy
    railway up --detach
    
    success "Railway deployment initiated!"
    echo ""
    log "Check deployment: railway status"
    log "View logs: railway logs"
    log "Open dashboard: railway open"
}

# Deploy to Heroku
deploy_heroku() {
    log "Deploying to Heroku..."
    cd "$PROJECT_ROOT"
    
    command -v heroku >/dev/null 2>&1 || error "Heroku CLI is required"
    
    APP_NAME="${HEROKU_APP_NAME:-finmind-app}"
    
    # Create app if doesn't exist
    heroku apps:info --app "$APP_NAME" 2>/dev/null || heroku create "$APP_NAME"
    
    # Add addons
    heroku addons:create heroku-postgresql:essential-0 --app "$APP_NAME" 2>/dev/null || true
    heroku addons:create heroku-redis:mini --app "$APP_NAME" 2>/dev/null || true
    
    # Set config
    heroku config:set LOG_LEVEL=INFO GEMINI_MODEL=gemini-1.5-flash --app "$APP_NAME"
    [ -n "$JWT_SECRET" ] && heroku config:set JWT_SECRET="$JWT_SECRET" --app "$APP_NAME"
    [ -n "$GEMINI_API_KEY" ] && heroku config:set GEMINI_API_KEY="$GEMINI_API_KEY" --app "$APP_NAME"
    
    # Deploy with container
    heroku container:push web --app "$APP_NAME" --context-path ./packages/backend
    heroku container:release web --app "$APP_NAME"
    
    success "Heroku deployment complete!"
    echo ""
    log "App URL: https://$APP_NAME.herokuapp.com"
    log "Logs: heroku logs --tail --app $APP_NAME"
}

# Deploy to Render (via API/Dashboard)
deploy_render() {
    log "Render deployment uses render.yaml blueprint"
    echo ""
    echo "To deploy to Render:"
    echo "1. Go to https://render.com/deploy"
    echo "2. Connect your GitHub repository"
    echo "3. Render will auto-detect deploy/render/render.yaml"
    echo ""
    echo "Or use the Deploy button in README.md"
}

# Show help
show_help() {
    echo "FinMind Universal Deployment Script"
    echo ""
    echo "Usage: $0 [platform] [environment]"
    echo ""
    echo "Platforms:"
    echo "  docker       - Docker Compose (development, default)"
    echo "  docker-prod  - Docker Compose (production)"
    echo "  kubernetes   - Raw Kubernetes manifests"
    echo "  helm         - Helm chart deployment"
    echo "  tilt         - Tilt local K8s development"
    echo "  fly          - Fly.io"
    echo "  railway      - Railway"
    echo "  heroku       - Heroku"
    echo "  render       - Render (instructions)"
    echo ""
    echo "Environment (used for Helm/K8s):"
    echo "  dev          - Development (default)"
    echo "  staging      - Staging"
    echo "  production   - Production"
    echo ""
    echo "Examples:"
    echo "  $0                    # Docker Compose dev"
    echo "  $0 docker-prod        # Docker Compose production"
    echo "  $0 helm production    # Helm to production K8s"
    echo "  $0 fly                # Deploy to Fly.io"
    echo ""
    echo "Environment variables:"
    echo "  JWT_SECRET        - JWT signing secret"
    echo "  POSTGRES_PASSWORD - PostgreSQL password (Helm)"
    echo "  GEMINI_API_KEY    - Google Gemini API key"
    echo "  HEROKU_APP_NAME   - Heroku app name"
}

# Main
case "$PLATFORM" in
    help|--help|-h)
        show_help
        ;;
    docker)
        check_prereqs
        setup_env
        deploy_docker
        ;;
    docker-prod)
        check_prereqs
        setup_env
        deploy_docker_prod
        ;;
    kubernetes|k8s)
        check_prereqs
        setup_env
        deploy_kubernetes
        ;;
    helm)
        check_prereqs
        setup_env
        deploy_helm
        ;;
    tilt)
        check_prereqs
        setup_env
        deploy_tilt
        ;;
    fly|flyio)
        check_prereqs
        setup_env
        deploy_fly
        ;;
    railway)
        check_prereqs
        setup_env
        deploy_railway
        ;;
    heroku)
        check_prereqs
        setup_env
        deploy_heroku
        ;;
    render)
        deploy_render
        ;;
    *)
        error "Unknown platform: $PLATFORM. Use '$0 help' for usage."
        ;;
esac
