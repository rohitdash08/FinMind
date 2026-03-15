#!/usr/bin/env bash
# =============================================================================
# FinMind — Local Development Environment Setup
# =============================================================================
# Sets up everything needed to run FinMind locally for development.
#
# Usage:
#   ./deploy/scripts/setup-local.sh [options]
#
# Options:
#   --docker       Use Docker Compose for local dev (default)
#   --tilt         Use Tilt + local Kubernetes for local dev
#   --bare         Set up without containers (Python + Node directly)
#   --skip-deps    Skip dependency installation checks
#   --help         Show this help message
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Defaults
MODE="docker"
SKIP_DEPS=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
    head -17 "$0" | tail -13
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker)    MODE="docker";  shift ;;
        --tilt)      MODE="tilt";    shift ;;
        --bare)      MODE="bare";    shift ;;
        --skip-deps) SKIP_DEPS=true; shift ;;
        --help|-h)   usage ;;
        *)           log_error "Unknown option: $1"; usage ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1: Create .env from example if it does not exist
# ---------------------------------------------------------------------------
setup_env() {
    if [ ! -f "${REPO_ROOT}/.env" ]; then
        log_info "Creating .env from .env.example..."
        cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"

        # Generate a random JWT secret for local development
        if command -v openssl &>/dev/null; then
            local jwt_secret
            jwt_secret=$(openssl rand -hex 32)
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s/JWT_SECRET=\"change-me\"/JWT_SECRET=\"${jwt_secret}\"/" "${REPO_ROOT}/.env"
            else
                sed -i "s/JWT_SECRET=\"change-me\"/JWT_SECRET=\"${jwt_secret}\"/" "${REPO_ROOT}/.env"
            fi
            log_ok "Generated random JWT_SECRET"
        else
            log_warn "openssl not found — please set JWT_SECRET in .env manually"
        fi

        log_ok ".env file created. Edit it to add API keys if needed."
    else
        log_ok ".env file already exists."
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Check system dependencies
# ---------------------------------------------------------------------------
check_dependencies() {
    if [ "$SKIP_DEPS" = true ]; then
        log_warn "Skipping dependency checks (--skip-deps)"
        return
    fi

    log_info "Checking system dependencies..."

    local missing=()

    case "$MODE" in
        docker)
            command -v docker &>/dev/null || missing+=("docker")
            ;;
        tilt)
            command -v docker &>/dev/null || missing+=("docker")
            command -v kubectl &>/dev/null || missing+=("kubectl")
            command -v tilt &>/dev/null || missing+=("tilt")
            ;;
        bare)
            command -v python3 &>/dev/null || missing+=("python3")
            command -v node &>/dev/null || missing+=("node (v20+)")
            command -v npm &>/dev/null || missing+=("npm")
            ;;
    esac

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_error "Please install them and try again."
        exit 1
    fi

    log_ok "All dependencies present."
}

# ---------------------------------------------------------------------------
# Step 3: Start services
# ---------------------------------------------------------------------------
start_docker() {
    log_info "Starting FinMind with Docker Compose (development mode)..."

    # Use the root docker-compose.yml which includes dev tools and hot-reload
    cd "${REPO_ROOT}"
    docker compose up -d --build

    log_ok "Development environment is running."
    echo ""
    log_info "Services:"
    log_info "  Frontend:    http://localhost:5173"
    log_info "  Backend API: http://localhost:8000"
    log_info "  Health:      http://localhost:8000/health"
    log_info "  Grafana:     http://localhost:3000"
    log_info "  Prometheus:  http://localhost:9090"
    echo ""
    log_info "Useful commands:"
    log_info "  docker compose logs -f backend    # Backend logs"
    log_info "  docker compose logs -f frontend-dev  # Frontend logs"
    log_info "  docker compose down               # Stop everything"
}

start_tilt() {
    log_info "Starting FinMind with Tilt (local Kubernetes)..."

    # Verify a Kubernetes cluster is running
    if ! kubectl cluster-info &>/dev/null; then
        log_error "No Kubernetes cluster found. Start Docker Desktop K8s, minikube, or kind."
        exit 1
    fi

    cd "${REPO_ROOT}/deploy/tilt"
    tilt up

    log_ok "Tilt is running. Open http://localhost:10350 for the Tilt dashboard."
}

start_bare() {
    log_info "Setting up bare-metal development environment..."

    # Backend
    log_info "Setting up Python backend..."
    cd "${REPO_ROOT}/packages/backend"

    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_ok "Created Python virtual environment"
    fi

    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install -r requirements.txt
    log_ok "Backend dependencies installed"

    # Frontend
    log_info "Setting up Node.js frontend..."
    cd "${REPO_ROOT}/app"
    npm ci
    log_ok "Frontend dependencies installed"

    echo ""
    log_info "Local setup complete. Start the services:"
    echo ""
    log_info "  Terminal 1 (PostgreSQL + Redis via Docker):"
    log_info "    docker compose up postgres redis"
    echo ""
    log_info "  Terminal 2 (Backend):"
    log_info "    cd packages/backend && source venv/bin/activate"
    log_info "    flask --app wsgi:app init-db"
    log_info "    flask --app wsgi:app run --port 8000 --reload"
    echo ""
    log_info "  Terminal 3 (Frontend):"
    log_info "    cd app && npm run dev"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
log_info "FinMind Local Development Setup (mode: ${MODE})"
echo ""

setup_env
check_dependencies

case "$MODE" in
    docker)  start_docker ;;
    tilt)    start_tilt ;;
    bare)    start_bare ;;
esac
