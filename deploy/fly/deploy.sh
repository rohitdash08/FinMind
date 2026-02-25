#!/bin/bash
set -euo pipefail

# FinMind — Fly.io Deployment Script
# ───────────────────────────────────
# Prerequisites: flyctl installed, authenticated
# Usage: ./deploy/fly/deploy.sh

REGION="${FLY_REGION:-sjc}"
BACKEND_APP="${FLY_BACKEND_APP:-finmind-backend}"
FRONTEND_APP="${FLY_FRONTEND_APP:-finmind-frontend}"

echo "╔══════════════════════════════════════════╗"
echo "║  FinMind — Fly.io Deployment             ║"
echo "╚══════════════════════════════════════════╝"
echo "  Region: $REGION"
echo ""

# ── 1. Create PostgreSQL ──────────────────────────
echo "🐘 Creating Fly PostgreSQL..."
if ! fly postgres list 2>/dev/null | grep -q finmind-db; then
  fly postgres create --name finmind-db --region "$REGION" --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1
fi

# ── 2. Create Redis ───────────────────────────────
echo "🔴 Creating Fly Redis (Upstash)..."
if ! fly redis list 2>/dev/null | grep -q finmind-redis; then
  fly redis create --name finmind-redis --region "$REGION" --no-eviction
fi

# ── 3. Launch Backend ─────────────────────────────
echo "🚀 Deploying backend..."
if ! fly apps list 2>/dev/null | grep -q "$BACKEND_APP"; then
  fly launch --name "$BACKEND_APP" --config deploy/fly/fly.toml --region "$REGION" --no-deploy --copy-config
fi

# Attach databases
fly postgres attach finmind-db --app "$BACKEND_APP" 2>/dev/null || true
fly redis attach finmind-redis --app "$BACKEND_APP" 2>/dev/null || true

# Set secrets
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
fly secrets set JWT_SECRET="$JWT_SECRET" --app "$BACKEND_APP"

# Deploy
fly deploy --config deploy/fly/fly.toml --app "$BACKEND_APP"

BACKEND_URL="https://${BACKEND_APP}.fly.dev"

# ── 4. Launch Frontend ────────────────────────────
echo "🚀 Deploying frontend..."
if ! fly apps list 2>/dev/null | grep -q "$FRONTEND_APP"; then
  fly launch --name "$FRONTEND_APP" --config deploy/fly/fly-frontend.toml --region "$REGION" --no-deploy --copy-config
fi

fly deploy --config deploy/fly/fly-frontend.toml --app "$FRONTEND_APP"

FRONTEND_URL="https://${FRONTEND_APP}.fly.dev"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ FinMind deployed to Fly.io!          ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Frontend: $FRONTEND_URL"
echo "║  Backend:  $BACKEND_URL"
echo "║  Health:   $BACKEND_URL/health"
echo "╚══════════════════════════════════════════╝"
