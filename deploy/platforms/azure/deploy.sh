#!/usr/bin/env bash
# Azure Container Apps Deployment Script
# Prerequisites: az CLI logged in, subscription set
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENV_NAME="finmind-env"
APP_NAME="finmind-backend"
ACR_NAME="${AZURE_ACR_NAME:-finmindacr}"

echo "======================================"
echo "  FinMind — Azure Container Apps Deploy"
echo "======================================"

# 1. Create resource group
echo "[1/7] Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none 2>/dev/null || true

# 2. Create ACR
echo "[2/7] Creating Container Registry..."
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" \
    --sku Basic --admin-enabled true --output none 2>/dev/null || true

# 3. Build and push image
echo "[3/7] Building and pushing image..."
az acr build --registry "$ACR_NAME" --image finmind-backend:latest \
    --file packages/backend/Dockerfile packages/backend/

# 4. Create Container Apps environment
echo "[4/7] Creating Container Apps environment..."
az containerapp env create \
    --name "$ENV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none 2>/dev/null || true

# 5. Create PostgreSQL
echo "[5/7] Creating Azure Database for PostgreSQL..."
PG_SERVER="finmind-pg-${RANDOM}"
PG_PASS=$(openssl rand -base64 24)
az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER" \
    --location "$LOCATION" \
    --admin-user finmind \
    --admin-password "$PG_PASS" \
    --sku-name Standard_B1ms \
    --version 16 \
    --output none 2>/dev/null || echo "  PostgreSQL already exists or creation in progress"

# 6. Create Redis
echo "[6/7] Creating Azure Cache for Redis..."
az redis create \
    --resource-group "$RESOURCE_GROUP" \
    --name "finmind-redis" \
    --location "$LOCATION" \
    --sku Basic \
    --vm-size C0 \
    --output none 2>/dev/null || echo "  Redis already exists or creation in progress"

# 7. Deploy Container App
echo "[7/7] Deploying Container App..."
ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query username --output tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' --output tsv)

az containerapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/finmind-backend:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 10 \
    --cpu 0.5 \
    --memory 1Gi \
    --env-vars "LOG_LEVEL=INFO" "GEMINI_MODEL=gemini-1.5-flash" \
    --output none

FQDN=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn --output tsv)

echo ""
echo "Deployed: https://${FQDN}"
echo "Health:   https://${FQDN}/health"
echo ""
echo "NOTE: Set DATABASE_URL, REDIS_URL, JWT_SECRET via:"
echo "  az containerapp update --name $APP_NAME --resource-group $RESOURCE_GROUP --set-env-vars 'DATABASE_URL=secretref:...' "
