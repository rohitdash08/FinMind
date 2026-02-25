#!/bin/bash
set -euo pipefail

# FinMind — Azure Container Apps Deployment Script
# ─────────────────────────────────────────────────
# Prerequisites: Azure CLI configured, Docker installed
# Usage: ./deploy/azure/deploy.sh

RESOURCE_GROUP="${AZURE_RG:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENV_NAME="finmind-env"
ACR_NAME="${AZURE_ACR:-finmindacr$(openssl rand -hex 3)}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"

echo "╔══════════════════════════════════════════╗"
echo "║  FinMind — Azure Container Apps Deploy   ║"
echo "╚══════════════════════════════════════════╝"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location:       $LOCATION"
echo ""

# ── 1. Create Resource Group ──────────────────────
echo "📦 Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# ── 2. Create Container Apps Environment ──────────
echo "🌐 Creating Container Apps environment..."
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none 2>/dev/null || true

# ── 3. Create PostgreSQL Flexible Server ──────────
echo "🐘 Creating PostgreSQL Flexible Server..."
if ! az postgres flexible-server show --name finmind-db --resource-group "$RESOURCE_GROUP" 2>/dev/null; then
  az postgres flexible-server create \
    --name finmind-db \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --admin-user finmind \
    --admin-password "$DB_PASSWORD" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --version 16 \
    --database-name finmind \
    --public-access 0.0.0.0 \
    --yes \
    --output none
fi

PG_HOST=$(az postgres flexible-server show \
  --name finmind-db --resource-group "$RESOURCE_GROUP" \
  --query fullyQualifiedDomainName -o tsv)

# ── 4. Create Azure Cache for Redis ───────────────
echo "🔴 Creating Azure Cache for Redis..."
if ! az redis show --name finmind-redis --resource-group "$RESOURCE_GROUP" 2>/dev/null; then
  az redis create \
    --name finmind-redis \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Basic \
    --vm-size c0 \
    --output none
fi

REDIS_HOST=$(az redis show --name finmind-redis --resource-group "$RESOURCE_GROUP" --query hostName -o tsv)
REDIS_KEY=$(az redis list-keys --name finmind-redis --resource-group "$RESOURCE_GROUP" --query primaryKey -o tsv)

# ── 5. Create ACR and Push Images ─────────────────
echo "📦 Creating Container Registry..."
az acr create --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --sku Basic --admin-enabled true --output none 2>/dev/null || true
az acr login --name "$ACR_NAME"

echo "🔨 Building and pushing backend..."
docker build -t "${ACR_NAME}.azurecr.io/api:latest" -f packages/backend/Dockerfile packages/backend/
docker push "${ACR_NAME}.azurecr.io/api:latest"

echo "🔨 Building and pushing frontend..."
docker build -t "${ACR_NAME}.azurecr.io/web:latest" -f app/Dockerfile app/
docker push "${ACR_NAME}.azurecr.io/web:latest"

ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' -o tsv)

# ── 6. Deploy Backend ─────────────────────────────
echo "🚀 Deploying backend..."
az containerapp create \
  --name finmind-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "${ACR_NAME}.azurecr.io/api:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    "DATABASE_URL=postgresql+psycopg2://finmind:${DB_PASSWORD}@${PG_HOST}:5432/finmind" \
    "REDIS_URL=rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0" \
    "JWT_SECRET=${JWT_SECRET}" \
    "GEMINI_MODEL=gemini-1.5-flash" \
    "LOG_LEVEL=INFO" \
  --output none

BACKEND_URL=$(az containerapp show --name finmind-api --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

# ── 7. Deploy Frontend ────────────────────────────
echo "🚀 Deploying frontend..."
az containerapp create \
  --name finmind-web \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "${ACR_NAME}.azurecr.io/web:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --output none

FRONTEND_URL=$(az containerapp show --name finmind-web --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ FinMind deployed to Azure!           ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Frontend: https://$FRONTEND_URL"
echo "║  Backend:  https://$BACKEND_URL"
echo "║  Health:   https://$BACKEND_URL/health"
echo "╠══════════════════════════════════════════╣"
echo "║  PostgreSQL: $PG_HOST"
echo "║  Redis:      $REDIS_HOST"
echo "╚══════════════════════════════════════════╝"
