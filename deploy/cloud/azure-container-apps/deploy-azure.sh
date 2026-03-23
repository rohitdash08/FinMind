#!/usr/bin/env bash
# deploy-azure.sh — Deploy FinMind to Azure Container Apps
# Usage: ./deploy-azure.sh [RESOURCE_GROUP] [LOCATION]
set -euo pipefail

RESOURCE_GROUP="${1:-finmind-rg}"
LOCATION="${2:-eastus}"
ENVIRONMENT="finmind-env"
BACKEND_IMAGE="ghcr.io/rohitdash08/finmind-backend:latest"
FRONTEND_IMAGE="ghcr.io/rohitdash08/finmind-frontend:latest"

echo "🚀 Deploying FinMind to Azure Container Apps"
echo "   Resource Group: ${RESOURCE_GROUP}"
echo "   Location: ${LOCATION}"

# ── Create resource group ────────────────────────────────────────────────────
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --output none

# ── Create Container Apps environment ────────────────────────────────────────
echo "🏗️  Creating Container Apps environment..."
az containerapp env create \
  --name "${ENVIRONMENT}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

# ── Create Azure Database for PostgreSQL (Flexible Server) ───────────────────
echo "🐘 Creating PostgreSQL server..."
PG_SERVER="finmind-pgserver"
PG_ADMIN_USER="finmindadmin"
PG_ADMIN_PASSWORD="$(openssl rand -base64 24)"

az postgres flexible-server create \
  --name "${PG_SERVER}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --admin-user "${PG_ADMIN_USER}" \
  --admin-password "${PG_ADMIN_PASSWORD}" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --version 16 \
  --storage-size 32 \
  --yes \
  --output none 2>/dev/null || echo "   (PostgreSQL server may already exist)"

az postgres flexible-server db create \
  --server-name "${PG_SERVER}" \
  --resource-group "${RESOURCE_GROUP}" \
  --database-name finmind \
  --output none 2>/dev/null || true

PG_FQDN=$(az postgres flexible-server show \
  --name "${PG_SERVER}" --resource-group "${RESOURCE_GROUP}" \
  --query "fullyQualifiedDomainName" -o tsv)

DATABASE_URL="postgresql+psycopg2://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_FQDN}:5432/finmind?sslmode=require"

# ── Create Azure Cache for Redis ─────────────────────────────────────────────
echo "📕 Creating Redis cache..."
REDIS_NAME="finmind-redis-$(openssl rand -hex 4)"
az redis create \
  --name "${REDIS_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --sku Basic \
  --vm-size C0 \
  --output none 2>/dev/null || echo "   (Redis cache may already exist)"

REDIS_HOST=$(az redis show --name "${REDIS_NAME}" --resource-group "${RESOURCE_GROUP}" \
  --query "hostName" -o tsv 2>/dev/null || echo "redis-placeholder")
REDIS_KEY=$(az redis list-keys --name "${REDIS_NAME}" --resource-group "${RESOURCE_GROUP}" \
  --query "primaryKey" -o tsv 2>/dev/null || echo "")
REDIS_URL="redis://:${REDIS_KEY}@${REDIS_HOST}:6380/0"

JWT_SECRET="$(openssl rand -hex 32)"

# ── Deploy backend ───────────────────────────────────────────────────────────
echo "🔧 Deploying backend..."
az containerapp create \
  --name finmind-backend \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${ENVIRONMENT}" \
  --image "${BACKEND_IMAGE}" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    "DATABASE_URL=${DATABASE_URL}" \
    "REDIS_URL=${REDIS_URL}" \
    "JWT_SECRET=${JWT_SECRET}" \
    "LOG_LEVEL=INFO" \
    "GEMINI_MODEL=gemini-1.5-flash" \
    "PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc" \
  --command "sh" "-c" \
    "python -m flask --app wsgi:app init-db && rm -rf /tmp/prometheus_multiproc && mkdir -p /tmp/prometheus_multiproc && gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app" \
  --output none

BACKEND_FQDN=$(az containerapp show \
  --name finmind-backend --resource-group "${RESOURCE_GROUP}" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo "✅ Backend deployed: https://${BACKEND_FQDN}"

# ── Deploy frontend ──────────────────────────────────────────────────────────
echo "🔧 Deploying frontend..."
az containerapp create \
  --name finmind-frontend \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${ENVIRONMENT}" \
  --image "${FRONTEND_IMAGE}" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --output none

FRONTEND_FQDN=$(az containerapp show \
  --name finmind-frontend --resource-group "${RESOURCE_GROUP}" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo "✅ Frontend deployed: https://${FRONTEND_FQDN}"

echo ""
echo "📋 Summary:"
echo "   Backend:  https://${BACKEND_FQDN}"
echo "   Frontend: https://${FRONTEND_FQDN}"
echo "   Postgres: ${PG_FQDN}"
echo ""
echo "⚠️  Save the database password: ${PG_ADMIN_PASSWORD}"
echo "⚠️  Rebuild frontend with VITE_API_URL=https://${BACKEND_FQDN}"
