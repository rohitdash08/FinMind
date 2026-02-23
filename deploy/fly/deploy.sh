#!/bin/bash
set -euo pipefail

# FinMind - Fly.io Deployment Script
# Usage: ./deploy/fly/deploy.sh

echo "🚀 Deploying FinMind to Fly.io..."

APP_PREFIX="${FLY_APP_PREFIX:-finmind}"
REGION="${FLY_REGION:-sjc}"

# Create backend app
echo "📦 Creating backend app..."
fly apps create "${APP_PREFIX}-api" --machines 2>/dev/null || true

# Create Postgres
echo "🐘 Creating PostgreSQL cluster..."
fly postgres create \
  --name "${APP_PREFIX}-db" \
  --region "$REGION" \
  --vm-size shared-cpu-1x \
  --volume-size 1 \
  --initial-cluster-size 1 2>/dev/null || echo "  (already exists)"

# Attach Postgres to backend
fly postgres attach "${APP_PREFIX}-db" --app "${APP_PREFIX}-api" 2>/dev/null || true

# Create Redis
echo "🔴 Creating Redis..."
fly redis create \
  --name "${APP_PREFIX}-redis" \
  --region "$REGION" \
  --plan free 2>/dev/null || echo "  (already exists)"

# Set backend secrets
echo "🔐 Setting secrets..."
JWT_SECRET=${JWT_SECRET:-$(openssl rand -hex 32)}
REDIS_URL=$(fly redis status "${APP_PREFIX}-redis" --app "${APP_PREFIX}-api" 2>/dev/null | grep "Private URL" | awk '{print $NF}' || echo "redis://default:@${APP_PREFIX}-redis.internal:6379")

fly secrets set \
  JWT_SECRET="$JWT_SECRET" \
  REDIS_URL="$REDIS_URL" \
  LOG_LEVEL="INFO" \
  --app "${APP_PREFIX}-api"

# Deploy backend
echo "🔨 Deploying backend..."
fly deploy \
  --config deploy/fly/fly.backend.toml \
  --app "${APP_PREFIX}-api" \
  --region "$REGION"

BACKEND_URL="https://${APP_PREFIX}-api.fly.dev"
echo "✅ Backend deployed: $BACKEND_URL"

# Create and deploy frontend
echo "📦 Creating frontend app..."
fly apps create "${APP_PREFIX}-web" --machines 2>/dev/null || true

# Build frontend with correct API URL
echo "🔨 Deploying frontend..."
fly deploy \
  --config deploy/fly/fly.frontend.toml \
  --app "${APP_PREFIX}-web" \
  --region "$REGION" \
  --build-arg "VITE_API_URL=$BACKEND_URL"

FRONTEND_URL="https://${APP_PREFIX}-web.fly.dev"
echo "✅ Frontend deployed: $FRONTEND_URL"

echo ""
echo "🎉 FinMind deployed successfully!"
echo "   Frontend: $FRONTEND_URL"
echo "   Backend:  $BACKEND_URL"
echo "   Health:   $BACKEND_URL/health"
