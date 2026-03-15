#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# FinMind — Fly.io Deployment Script
# Deploys backend + frontend services with managed Postgres & Redis
#
# Prerequisites:
#   brew install flyctl   (or curl -L https://fly.io/install.sh | sh)
#   flyctl auth login
#
# Usage:
#   ./deploy.sh              # full deploy (infra + apps)
#   ./deploy.sh apps         # deploy apps only (skip infra)
#   ./deploy.sh infra        # provision infra only
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGION="${FLY_REGION:-sjc}"

BACKEND_APP="finmind-backend"
FRONTEND_APP="finmind-frontend"
PG_APP="finmind-db"
REDIS_NAME="finmind-redis"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[FinMind]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()   { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

# ── Preflight ────────────────────────────────────────────────
preflight() {
  if ! command -v flyctl &>/dev/null; then
    err "flyctl not found. Install: curl -L https://fly.io/install.sh | sh"
    exit 1
  fi

  if ! flyctl auth whoami &>/dev/null; then
    err "Not authenticated. Run: flyctl auth login"
    exit 1
  fi

  log "Authenticated as $(flyctl auth whoami)"
}

# ── Provision Infrastructure ─────────────────────────────────
provision_infra() {
  log "Provisioning infrastructure in region: $REGION"

  # PostgreSQL
  if flyctl postgres list 2>/dev/null | grep -q "$PG_APP"; then
    ok "Postgres cluster '$PG_APP' already exists"
  else
    log "Creating Postgres cluster '$PG_APP'..."
    flyctl postgres create \
      --name "$PG_APP" \
      --region "$REGION" \
      --vm-size shared-cpu-1x \
      --initial-cluster-size 1 \
      --volume-size 10
    ok "Postgres cluster created"
  fi

  # Redis (Upstash)
  if flyctl redis list 2>/dev/null | grep -q "$REDIS_NAME"; then
    ok "Redis '$REDIS_NAME' already exists"
  else
    log "Creating Redis instance '$REDIS_NAME'..."
    flyctl redis create \
      --name "$REDIS_NAME" \
      --region "$REGION" \
      --no-replicas
    ok "Redis instance created"
  fi
}

# ── Deploy Backend ───────────────────────────────────────────
deploy_backend() {
  log "Deploying backend..."
  cd "$PROJECT_ROOT"

  # Launch or deploy
  if flyctl apps list 2>/dev/null | grep -q "$BACKEND_APP"; then
    log "App '$BACKEND_APP' exists — deploying..."
    flyctl deploy \
      --app "$BACKEND_APP" \
      --config "$SCRIPT_DIR/fly.backend.toml" \
      --dockerfile packages/backend/Dockerfile \
      --strategy rolling \
      --wait-timeout 300
  else
    log "Creating app '$BACKEND_APP'..."
    flyctl launch \
      --name "$BACKEND_APP" \
      --config "$SCRIPT_DIR/fly.backend.toml" \
      --dockerfile packages/backend/Dockerfile \
      --region "$REGION" \
      --no-deploy

    # Attach Postgres
    log "Attaching Postgres..."
    flyctl postgres attach "$PG_APP" --app "$BACKEND_APP" || warn "Postgres may already be attached"

    # Set secrets
    log "Setting secrets (you'll be prompted for values)..."
    if [[ -z "${JWT_SECRET:-}" ]]; then
      JWT_SECRET=$(openssl rand -hex 64)
      warn "Generated JWT_SECRET automatically"
    fi

    flyctl secrets set \
      JWT_SECRET="$JWT_SECRET" \
      GEMINI_API_KEY="${GEMINI_API_KEY:-changeme}" \
      --app "$BACKEND_APP"

    # Deploy
    flyctl deploy \
      --app "$BACKEND_APP" \
      --config "$SCRIPT_DIR/fly.backend.toml" \
      --dockerfile packages/backend/Dockerfile \
      --strategy rolling \
      --wait-timeout 300
  fi

  ok "Backend deployed: https://$BACKEND_APP.fly.dev"
}

# ── Deploy Frontend ──────────────────────────────────────────
deploy_frontend() {
  log "Deploying frontend..."
  cd "$PROJECT_ROOT"

  if flyctl apps list 2>/dev/null | grep -q "$FRONTEND_APP"; then
    log "App '$FRONTEND_APP' exists — deploying..."
    flyctl deploy \
      --app "$FRONTEND_APP" \
      --config "$SCRIPT_DIR/fly.frontend.toml" \
      --dockerfile app/Dockerfile \
      --strategy rolling \
      --wait-timeout 180
  else
    log "Creating app '$FRONTEND_APP'..."
    flyctl launch \
      --name "$FRONTEND_APP" \
      --config "$SCRIPT_DIR/fly.frontend.toml" \
      --dockerfile app/Dockerfile \
      --region "$REGION" \
      --no-deploy

    flyctl deploy \
      --app "$FRONTEND_APP" \
      --config "$SCRIPT_DIR/fly.frontend.toml" \
      --dockerfile app/Dockerfile \
      --strategy rolling \
      --wait-timeout 180
  fi

  ok "Frontend deployed: https://$FRONTEND_APP.fly.dev"
}

# ── Health Check ─────────────────────────────────────────────
check_health() {
  log "Running health checks..."

  local backend_url="https://$BACKEND_APP.fly.dev/health"
  local frontend_url="https://$FRONTEND_APP.fly.dev/"

  for url in "$backend_url" "$frontend_url"; do
    if curl -sf --max-time 10 "$url" > /dev/null 2>&1; then
      ok "$url — healthy"
    else
      warn "$url — not responding (may still be starting)"
    fi
  done
}

# ── Main ─────────────────────────────────────────────────────
main() {
  preflight

  case "${1:-all}" in
    infra)
      provision_infra
      ;;
    apps)
      deploy_backend
      deploy_frontend
      check_health
      ;;
    backend)
      deploy_backend
      ;;
    frontend)
      deploy_frontend
      ;;
    all)
      provision_infra
      deploy_backend
      deploy_frontend
      check_health
      ;;
    *)
      echo "Usage: $0 {all|infra|apps|backend|frontend}"
      exit 1
      ;;
  esac

  echo ""
  ok "Deployment complete!"
  log "Backend:  https://$BACKEND_APP.fly.dev"
  log "Frontend: https://$FRONTEND_APP.fly.dev"
  log "Health:   https://$BACKEND_APP.fly.dev/health"
}

main "$@"
