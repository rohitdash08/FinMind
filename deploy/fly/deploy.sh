#!/usr/bin/env bash
# Deploy FinMind to Fly.io
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== FinMind Fly.io Deployment ==="

# Check fly CLI
if ! command -v fly &>/dev/null; then
  echo "Error: flyctl not found."
  echo "Install: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi

# Check authentication
if ! fly auth whoami &>/dev/null 2>&1; then
  echo "Not logged in. Running 'fly auth login'..."
  fly auth login
fi

echo ""
echo "Step 1: Creating Postgres cluster..."
fly postgres create --name finmind-db --region iad \
  --vm-size shared-cpu-1x --initial-cluster-size 1 --volume-size 1 \
  2>/dev/null || echo "  (Postgres cluster 'finmind-db' may already exist, continuing)"

echo ""
echo "Step 2: Creating Redis (via Upstash)..."
fly redis create --name finmind-redis --region iad --no-replicas \
  2>/dev/null || echo "  (Redis 'finmind-redis' may already exist, continuing)"

echo ""
echo "Step 3: Deploying backend..."
cd "$REPO_ROOT/packages/backend"
fly deploy --config "$SCRIPT_DIR/fly.backend.toml" --remote-only

echo ""
echo "Step 4: Attaching Postgres to backend..."
fly postgres attach finmind-db --app finmind-backend \
  2>/dev/null || echo "  (Already attached)"

echo ""
echo "Step 5: Setting secrets on backend..."
# Try to get Redis URL from Upstash
REDIS_URL=$(fly redis status finmind-redis --json 2>/dev/null | grep -o '"url":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
if [ -n "$REDIS_URL" ]; then
  fly secrets set --app finmind-backend \
    JWT_SECRET="$(openssl rand -hex 32)" \
    REDIS_URL="$REDIS_URL"
  echo "  Redis URL set automatically from Upstash."
else
  fly secrets set --app finmind-backend \
    JWT_SECRET="$(openssl rand -hex 32)"
  echo ""
  echo "  ⚠️  Could not auto-detect Redis URL."
  echo "  Set it manually: fly secrets set --app finmind-backend REDIS_URL=<your-redis-url>"
  echo "  (Check 'fly redis status finmind-redis' for the connection string)"
fi

echo ""
echo "Step 6: Deploying frontend..."
cd "$REPO_ROOT/app"
fly deploy --config "$SCRIPT_DIR/fly.frontend.toml" --remote-only

echo ""
echo "=== ✅ Deployment complete ==="
echo ""
echo "Backend:  https://finmind-backend.fly.dev/health"
echo "Frontend: https://finmind-frontend.fly.dev"
echo ""
echo "Next steps:"
echo "  1. Set VITE_API_URL on the frontend if needed"
echo "  2. Verify: curl https://finmind-backend.fly.dev/health"
echo "  3. Open https://finmind-frontend.fly.dev in your browser"
