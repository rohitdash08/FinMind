#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  FinMind — Universal One-Click Deployment Dispatcher        ║
# ║  Usage: ./deploy/scripts/deploy.sh <platform>               ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════╗"
    echo "║        FinMind Deploy Dispatcher         ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_usage() {
    echo "Usage: $0 <platform>"
    echo ""
    echo "Platforms:"
    echo "  docker-compose    Local Docker Compose (recommended for development)"
    echo "  kubernetes        Kubernetes via Helm chart"
    echo "  tilt              Local K8s dev with Tilt (hot-reload)"
    echo ""
    echo "  railway           Railway PaaS"
    echo "  heroku            Heroku (Docker stack)"
    echo "  render            Render Blueprint"
    echo "  flyio             Fly.io"
    echo "  digitalocean      DigitalOcean App Platform"
    echo "  do-droplet        DigitalOcean Droplet (Docker Compose)"
    echo ""
    echo "  aws-ecs           AWS ECS Fargate"
    echo "  aws-apprunner     AWS App Runner"
    echo "  gcp-cloudrun      GCP Cloud Run"
    echo "  azure             Azure Container Apps"
    echo ""
    echo "  netlify           Netlify (frontend only)"
    echo "  vercel            Vercel (frontend only)"
    echo ""
    echo "  smoke-test        Run smoke tests against a running deployment"
    echo "  validate          Validate all deployment configs"
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}ERROR: '$1' is required but not installed.${NC}"
        echo "Install it first: $2"
        exit 1
    fi
}

# ─── Pre-flight checks ───
preflight_docker() {
    check_command docker "https://docs.docker.com/get-docker/"
    if ! docker info &>/dev/null; then
        echo -e "${RED}ERROR: Docker daemon is not running.${NC}"
        exit 1
    fi
}

preflight_k8s() {
    check_command kubectl "https://kubernetes.io/docs/tasks/tools/"
    check_command helm "https://helm.sh/docs/intro/install/"
    if ! kubectl cluster-info &>/dev/null; then
        echo -e "${RED}ERROR: Cannot connect to Kubernetes cluster.${NC}"
        exit 1
    fi
}

# ─── Deploy functions ───
deploy_docker_compose() {
    preflight_docker
    echo -e "${GREEN}Deploying with Docker Compose...${NC}"

    if [ ! -f .env ]; then
        echo -e "${YELLOW}Creating .env from .env.example...${NC}"
        cp .env.example .env
    fi

    docker compose up -d --build

    echo -e "${GREEN}Done! Services:${NC}"
    echo "  Frontend:  http://localhost:5173"
    echo "  Backend:   http://localhost:8000"
    echo "  Grafana:   http://localhost:3000"
    echo ""
    echo "Run smoke tests: $0 smoke-test"
}

deploy_kubernetes() {
    preflight_k8s
    echo -e "${GREEN}Deploying to Kubernetes via Helm...${NC}"

    # Install or upgrade
    helm upgrade --install finmind deploy/helm/finmind \
        --namespace finmind \
        --create-namespace \
        --wait \
        --timeout 5m

    echo -e "${GREEN}Done! Check status:${NC}"
    echo "  kubectl get pods -n finmind"
    echo "  kubectl get svc -n finmind"
    echo "  kubectl get ingress -n finmind"
}

deploy_tilt() {
    check_command tilt "https://docs.tilt.dev/install.html"
    preflight_docker
    echo -e "${GREEN}Starting Tilt local K8s dev environment...${NC}"
    echo "  This will build images, deploy to local K8s, and start live-reload."
    echo ""
    tilt up
}

deploy_railway() {
    check_command railway "https://docs.railway.app/develop/cli"
    echo -e "${GREEN}Deploying to Railway...${NC}"
    cp deploy/platforms/railway/railway.toml .
    railway up
    rm -f railway.toml
}

deploy_heroku() {
    check_command heroku "https://devcenter.heroku.com/articles/heroku-cli"
    echo -e "${GREEN}Deploying to Heroku...${NC}"
    cp deploy/platforms/heroku/Procfile .
    cp deploy/platforms/heroku/heroku.yml .
    heroku container:push web --recursive
    heroku container:release web
    rm -f Procfile heroku.yml
}

deploy_render() {
    echo -e "${GREEN}Deploying to Render...${NC}"
    echo "Render uses render.yaml for Blueprint deployments."
    echo ""
    echo "Steps:"
    echo "  1. Push this repo to GitHub"
    echo "  2. Go to https://dashboard.render.com/blueprints"
    echo "  3. Click 'New Blueprint Instance'"
    echo "  4. Select this repo — Render will auto-detect deploy/platforms/render/render.yaml"
    echo ""
    echo "Or copy render.yaml to repo root:"
    echo "  cp deploy/platforms/render/render.yaml ."
}

deploy_flyio() {
    check_command fly "https://fly.io/docs/hands-on/install-flyctl/"
    echo -e "${GREEN}Deploying to Fly.io...${NC}"

    echo "  Deploying backend..."
    fly deploy --config deploy/platforms/flyio/backend/fly.toml

    echo "  Deploying frontend..."
    fly deploy --config deploy/platforms/flyio/frontend/fly.toml

    echo -e "${GREEN}Done!${NC}"
    fly status --config deploy/platforms/flyio/backend/fly.toml
}

deploy_digitalocean() {
    check_command doctl "https://docs.digitalocean.com/reference/doctl/how-to/install/"
    echo -e "${GREEN}Deploying to DigitalOcean App Platform...${NC}"
    doctl apps create --spec deploy/platforms/digitalocean/app-platform/do-app-spec.yaml
}

deploy_do_droplet() {
    echo -e "${GREEN}Deploying to DigitalOcean Droplet...${NC}"
    echo "Run on the droplet:"
    echo "  curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean/droplet/setup.sh | sudo bash"
}

deploy_aws_ecs() {
    check_command aws "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    preflight_docker
    echo -e "${GREEN}Deploying to AWS ECS Fargate...${NC}"
    bash deploy/platforms/aws/ecs-fargate/deploy.sh
}

deploy_aws_apprunner() {
    check_command aws "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    echo -e "${GREEN}Deploying to AWS App Runner...${NC}"
    echo "Use the AWS Console or CLI:"
    echo "  aws apprunner create-service --cli-input-yaml file://deploy/platforms/aws/app-runner/apprunner.yaml"
}

deploy_gcp_cloudrun() {
    check_command gcloud "https://cloud.google.com/sdk/docs/install"
    echo -e "${GREEN}Deploying to GCP Cloud Run...${NC}"
    bash deploy/platforms/gcp/deploy.sh
}

deploy_azure() {
    check_command az "https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
    echo -e "${GREEN}Deploying to Azure Container Apps...${NC}"
    bash deploy/platforms/azure/deploy.sh
}

deploy_netlify() {
    check_command netlify "npm install -g netlify-cli"
    echo -e "${GREEN}Deploying frontend to Netlify...${NC}"
    cp deploy/platforms/netlify/netlify.toml app/
    cd app && netlify deploy --prod
    rm -f netlify.toml
}

deploy_vercel() {
    check_command vercel "npm install -g vercel"
    echo -e "${GREEN}Deploying frontend to Vercel...${NC}"
    cp deploy/platforms/vercel/vercel.json .
    vercel --prod
    rm -f vercel.json
}

run_smoke_test() {
    BACKEND_URL="${1:-http://localhost:8000}"
    FRONTEND_URL="${2:-http://localhost:5173}"
    bash "$SCRIPT_DIR/smoke-test.sh" "$BACKEND_URL" "$FRONTEND_URL"
}

validate_configs() {
    echo -e "${BLUE}Validating deployment configurations...${NC}"
    ERRORS=0

    # Validate Helm chart
    if command -v helm &>/dev/null; then
        echo -n "  Helm chart lint: "
        if helm lint deploy/helm/finmind &>/dev/null; then
            echo -e "${GREEN}PASS${NC}"
        else
            echo -e "${RED}FAIL${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    fi

    # Check required files exist
    for f in \
        deploy/platforms/railway/railway.toml \
        deploy/platforms/heroku/Procfile \
        deploy/platforms/heroku/app.json \
        deploy/platforms/render/render.yaml \
        deploy/platforms/flyio/backend/fly.toml \
        deploy/platforms/flyio/frontend/fly.toml \
        deploy/platforms/digitalocean/app-platform/do-app-spec.yaml \
        deploy/platforms/digitalocean/droplet/setup.sh \
        deploy/platforms/aws/ecs-fargate/task-definition.json \
        deploy/platforms/aws/app-runner/apprunner.yaml \
        deploy/platforms/gcp/cloudrun.yaml \
        deploy/platforms/azure/container-app.yaml \
        deploy/platforms/netlify/netlify.toml \
        deploy/platforms/vercel/vercel.json \
        Tiltfile \
    ; do
        echo -n "  $f: "
        if [ -f "$f" ]; then
            echo -e "${GREEN}EXISTS${NC}"
        else
            echo -e "${RED}MISSING${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done

    # Validate JSON files
    for f in deploy/platforms/aws/ecs-fargate/task-definition.json deploy/platforms/vercel/vercel.json deploy/platforms/heroku/app.json; do
        echo -n "  JSON valid ($f): "
        if python3 -m json.tool "$f" &>/dev/null; then
            echo -e "${GREEN}PASS${NC}"
        else
            echo -e "${RED}FAIL${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done

    echo ""
    if [ "$ERRORS" -eq 0 ]; then
        echo -e "${GREEN}All validations passed!${NC}"
    else
        echo -e "${RED}$ERRORS validation(s) failed.${NC}"
        exit 1
    fi
}

# ─── Main ───
print_header

if [ $# -eq 0 ]; then
    print_usage
    exit 0
fi

case "$1" in
    docker-compose|docker|compose)  deploy_docker_compose ;;
    kubernetes|k8s|helm)            deploy_kubernetes ;;
    tilt)                           deploy_tilt ;;
    railway)                        deploy_railway ;;
    heroku)                         deploy_heroku ;;
    render)                         deploy_render ;;
    flyio|fly)                      deploy_flyio ;;
    digitalocean|do)                deploy_digitalocean ;;
    do-droplet|droplet)             deploy_do_droplet ;;
    aws-ecs|ecs)                    deploy_aws_ecs ;;
    aws-apprunner|apprunner)        deploy_aws_apprunner ;;
    gcp-cloudrun|cloudrun|gcp)      deploy_gcp_cloudrun ;;
    azure)                          deploy_azure ;;
    netlify)                        deploy_netlify ;;
    vercel)                         deploy_vercel ;;
    smoke-test|test)                run_smoke_test "${2:-}" "${3:-}" ;;
    validate)                       validate_configs ;;
    *)
        echo -e "${RED}Unknown platform: $1${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac
