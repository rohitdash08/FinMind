#!/usr/bin/env bash
# =============================================================================
# FinMind - Universal One-Click Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh [command] [options]
#
# Commands:
#   docker      Deploy with Docker Compose (default)
#   k8s         Deploy to Kubernetes via Helm
#   tilt        Start Tilt local dev environment
#   status      Show deployment status
#   teardown    Remove all deployed resources
#
# Options:
#   --prod      Use production configuration
#   --dev       Use development configuration (default)
#   --build     Force rebuild images
#   --help      Show this help message
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants & Colors
# ---------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}" && pwd)"
readonly HELM_CHART="${PROJECT_ROOT}/deploy/helm/finmind"
readonly HELM_RELEASE="finmind"
readonly K8S_NAMESPACE="finmind"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

banner() {
    echo -e "${CYAN}"
    echo "  ╔═══════════════════════════════════════════════╗"
    echo "  ║       FinMind - Universal Deployment          ║"
    echo "  ║   Docker · Kubernetes · Tilt · One Click      ║"
    echo "  ╚═══════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        log_error "$1 is required but not installed."
        echo "  Install: $2"
        return 1
    fi
    log_success "$1 found: $(command -v "$1")"
}

# ---------------------------------------------------------------------------
# Environment Setup
# ---------------------------------------------------------------------------
setup_env() {
    if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
        if [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
            cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
            log_warn ".env created from .env.example — please review and update secrets!"
        else
            log_error "No .env or .env.example found. Cannot proceed."
            exit 1
        fi
    else
        log_success ".env file found"
    fi
}

# ---------------------------------------------------------------------------
# Docker Compose Deployment
# ---------------------------------------------------------------------------
deploy_docker() {
    local mode="${1:-dev}"
    local build_flag="${2:-}"

    log_info "Deploying with Docker Compose (${mode} mode)..."

    check_command "docker" "https://docs.docker.com/get-docker/"
    setup_env

    local compose_file="docker-compose.yml"
    if [[ "${mode}" == "prod" ]]; then
        compose_file="docker-compose.prod.yml"
    fi

    local cmd="docker compose -f ${PROJECT_ROOT}/${compose_file}"

    if [[ -n "${build_flag}" ]]; then
        log_info "Building images..."
        ${cmd} build
    fi

    log_info "Starting services..."
    ${cmd} up -d

    log_info "Waiting for services to be healthy..."
    sleep 10

    # Health check
    local retries=30
    local count=0
    while [[ ${count} -lt ${retries} ]]; do
        if docker compose -f "${PROJECT_ROOT}/${compose_file}" ps | grep -q "healthy"; then
            break
        fi
        count=$((count + 1))
        sleep 2
    done

    echo ""
    log_success "FinMind deployed successfully with Docker Compose!"
    echo ""
    if [[ "${mode}" == "prod" ]]; then
        echo -e "  ${CYAN}Frontend:${NC}  http://localhost:80"
        echo -e "  ${CYAN}Backend:${NC}   http://localhost:80/api"
        echo -e "  ${CYAN}Health:${NC}    http://localhost:80/health"
    else
        echo -e "  ${CYAN}Frontend:${NC}  http://localhost:5173"
        echo -e "  ${CYAN}Backend:${NC}   http://localhost:8000"
        echo -e "  ${CYAN}Nginx:${NC}     http://localhost:8080"
        echo -e "  ${CYAN}Grafana:${NC}   http://localhost:3000"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Kubernetes Deployment (Helm)
# ---------------------------------------------------------------------------
deploy_k8s() {
    local mode="${1:-dev}"

    log_info "Deploying to Kubernetes via Helm (${mode} mode)..."

    check_command "kubectl" "https://kubernetes.io/docs/tasks/tools/"
    check_command "helm" "https://helm.sh/docs/intro/install/"

    # Verify cluster connectivity
    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi
    log_success "Kubernetes cluster reachable"

    local values_override=""
    if [[ "${mode}" == "dev" ]]; then
        values_override="-f ${PROJECT_ROOT}/deploy/tilt/values-dev.yaml"
    fi

    # Install or upgrade the Helm release
    log_info "Installing/upgrading Helm release '${HELM_RELEASE}'..."
    helm upgrade --install "${HELM_RELEASE}" "${HELM_CHART}" \
        --namespace "${K8S_NAMESPACE}" \
        --create-namespace \
        ${values_override} \
        --wait \
        --timeout 5m

    log_info "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod \
        -l "app.kubernetes.io/instance=${HELM_RELEASE}" \
        -n "${K8S_NAMESPACE}" \
        --timeout=300s 2>/dev/null || true

    echo ""
    log_success "FinMind deployed to Kubernetes!"
    echo ""
    echo -e "  ${CYAN}Namespace:${NC}  ${K8S_NAMESPACE}"
    echo -e "  ${CYAN}Release:${NC}    ${HELM_RELEASE}"
    echo ""
    echo "  Useful commands:"
    echo "    kubectl get pods -n ${K8S_NAMESPACE}"
    echo "    kubectl get svc -n ${K8S_NAMESPACE}"
    echo "    kubectl logs -f deploy/backend -n ${K8S_NAMESPACE}"
    echo ""

    # Port-forward hint
    echo "  Quick access (port-forward):"
    echo "    kubectl port-forward svc/backend 8000:8000 -n ${K8S_NAMESPACE}"
    echo "    kubectl port-forward svc/frontend 5173:80 -n ${K8S_NAMESPACE}"
    echo ""
}

# ---------------------------------------------------------------------------
# Tilt Local Development
# ---------------------------------------------------------------------------
deploy_tilt() {
    log_info "Starting Tilt local development environment..."

    check_command "tilt" "https://docs.tilt.dev/install.html"
    check_command "docker" "https://docs.docker.com/get-docker/"
    check_command "kubectl" "https://kubernetes.io/docs/tasks/tools/"

    setup_env

    cd "${PROJECT_ROOT}"
    log_info "Launching Tilt UI..."
    echo ""
    echo -e "  ${CYAN}Tilt UI:${NC}    http://localhost:10350"
    echo -e "  ${CYAN}Frontend:${NC}   http://localhost:5173"
    echo -e "  ${CYAN}Backend:${NC}    http://localhost:8000"
    echo ""
    exec tilt up
}

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
show_status() {
    banner
    echo "=== Docker Compose ==="
    if command -v docker &>/dev/null; then
        docker compose ps 2>/dev/null || echo "  No Docker Compose services running"
    else
        echo "  Docker not installed"
    fi

    echo ""
    echo "=== Kubernetes ==="
    if command -v kubectl &>/dev/null; then
        kubectl get pods -n "${K8S_NAMESPACE}" 2>/dev/null || echo "  No K8s resources found"
        echo ""
        kubectl get svc -n "${K8S_NAMESPACE}" 2>/dev/null || true
    else
        echo "  kubectl not installed"
    fi
}

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------
teardown() {
    local target="${1:-all}"
    log_warn "Tearing down FinMind deployment..."

    if [[ "${target}" == "all" || "${target}" == "docker" ]]; then
        log_info "Stopping Docker Compose services..."
        docker compose -f "${PROJECT_ROOT}/docker-compose.yml" down -v 2>/dev/null || true
        docker compose -f "${PROJECT_ROOT}/docker-compose.prod.yml" down -v 2>/dev/null || true
    fi

    if [[ "${target}" == "all" || "${target}" == "k8s" ]]; then
        log_info "Removing Helm release..."
        helm uninstall "${HELM_RELEASE}" -n "${K8S_NAMESPACE}" 2>/dev/null || true
        kubectl delete namespace "${K8S_NAMESPACE}" 2>/dev/null || true
    fi

    if [[ "${target}" == "all" || "${target}" == "tilt" ]]; then
        log_info "Stopping Tilt..."
        tilt down 2>/dev/null || true
    fi

    log_success "Teardown complete."
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
show_help() {
    banner
    echo "Usage: ./deploy.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  docker      Deploy with Docker Compose (default)"
    echo "  k8s         Deploy to Kubernetes via Helm"
    echo "  tilt        Start Tilt local dev environment"
    echo "  status      Show deployment status"
    echo "  teardown    Remove all deployed resources"
    echo ""
    echo "Options:"
    echo "  --prod      Use production configuration"
    echo "  --dev       Use development configuration (default)"
    echo "  --build     Force rebuild images"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh docker --dev          # Dev with Docker Compose"
    echo "  ./deploy.sh docker --prod --build # Production with rebuild"
    echo "  ./deploy.sh k8s --prod            # Deploy to K8s cluster"
    echo "  ./deploy.sh tilt                  # Local dev with Tilt"
    echo "  ./deploy.sh teardown              # Remove everything"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local command="${1:-docker}"
    local mode="dev"
    local build_flag=""

    # Parse options
    shift || true
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prod)  mode="prod" ;;
            --dev)   mode="dev" ;;
            --build) build_flag="--build" ;;
            --help)  show_help; exit 0 ;;
            *)       log_error "Unknown option: $1"; show_help; exit 1 ;;
        esac
        shift
    done

    banner

    case "${command}" in
        docker)   deploy_docker "${mode}" "${build_flag}" ;;
        k8s)      deploy_k8s "${mode}" ;;
        tilt)     deploy_tilt ;;
        status)   show_status ;;
        teardown) teardown ;;
        --help)   show_help ;;
        *)        log_error "Unknown command: ${command}"; show_help; exit 1 ;;
    esac
}

main "$@"
