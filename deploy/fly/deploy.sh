#!/usr/bin/env bash
# Deploy FinMind to Fly.io
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== FinMind Fly.io Deployment ==="

# Check fly CLI
if ! command -v fly &>/dev/null; then
  echo "Install flyctl: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi

echo "Creating Postgres cluster..."
fly postgres create --name finmind-db --region iad --vm-size shared-cpu-1x --initial-cluster-size 1 --volume-size 1 || echo "Postgres may already exist"

echo "Creating Redis..."
fly redis create --name finmind-redis --region iad --plan free || echo "Redis may already exist"

echo "Deploying backend..."
cd "$REPO_ROOT"
fly deploy --config "$SCRIPT_DIR/fly.backend.toml" --remote-only

echo "Attaching Postgres to backend..."
fly postgres attach finmind-db --app finmind-backend || echo "Already attached"

echo "Setting secrets on backend..."
fly secrets set --app finmind-backend \
  JWT_SECRET="$(openssl rand -hex 32)" \
  REDIS_URL="$(fly redis status finmind-redis --app finmind-backend | grep 'URL' | awk '{print $2}')" \
  2>/dev/null || echo "Set secrets manually if needed"

echo "Deploying frontend..."
fly deploy --config "$SCRIPT_DIR/fly.frontend.toml" --dockerfile app/Dockerfile --remote-only

echo ""
echo "=== Deployment complete ==="
echo "Backend:  https://finmind-backend.fly.dev/health"
echo "Frontend: https://finmind-frontend.fly.dev"
