#!/usr/bin/env bash
# ============================================================================
# FinMind — Azure Container Apps Deployment Script
# ============================================================================
# Deploys backend (Python/Flask) + frontend (React/nginx) to Azure Container
# Apps with Azure Database for PostgreSQL Flexible Server and Azure Cache
# for Redis.
#
# Prerequisites:
#   - Azure CLI authenticated (az login)
#   - Docker installed and running
#
# Usage:
#   ./deploy.sh [--resource-group finmind-rg] [--location eastus]
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
PROJECT_NAME="finmind"
ENVIRONMENT_NAME="${PROJECT_NAME}-env"
ACR_NAME="${PROJECT_NAME}acr"
BACKEND_APP="${PROJECT_NAME}-backend"
FRONTEND_APP="${PROJECT_NAME}-frontend"
PG_SERVER="${PROJECT_NAME}-pgserver"
PG_DB="finmind"
PG_ADMIN="finmindadmin"
REDIS_NAME="${PROJECT_NAME}-redis"
BACKEND_DOCKERFILE="packages/backend/Dockerfile"
FRONTEND_DOCKERFILE="app/Dockerfile"

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --location)       LOCATION="$2"; shift 2 ;;
    *)                echo "Unknown option: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== FinMind Azure Container Apps Deployment ==="
echo "Resource Group: ${RESOURCE_GROUP}"
echo "Location:       ${LOCATION}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Create resource group
# ---------------------------------------------------------------------------
echo ">>> Step 1: Creating resource group..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --tags app=finmind environment=production \
  --output none

# ---------------------------------------------------------------------------
# Step 2: Create Azure Container Registry
# ---------------------------------------------------------------------------
echo ">>> Step 2: Creating Azure Container Registry..."
az acr create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --admin-enabled true \
  --output none 2>/dev/null || echo "  ACR already exists."

ACR_LOGIN_SERVER=$(az acr show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --query loginServer --output tsv)

# Login to ACR
az acr login --name "${ACR_NAME}"
echo "  ACR: ${ACR_LOGIN_SERVER}"

# ---------------------------------------------------------------------------
# Step 3: Build and push Docker images
# ---------------------------------------------------------------------------
echo ">>> Step 3: Building and pushing Docker images..."
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"

# Backend
echo "  Building backend..."
docker build \
  -t "${ACR_LOGIN_SERVER}/${BACKEND_APP}:${IMAGE_TAG}" \
  -t "${ACR_LOGIN_SERVER}/${BACKEND_APP}:latest" \
  -f "${PROJECT_ROOT}/${BACKEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/packages/backend"

docker push "${ACR_LOGIN_SERVER}/${BACKEND_APP}:${IMAGE_TAG}"
docker push "${ACR_LOGIN_SERVER}/${BACKEND_APP}:latest"

# Frontend
echo "  Building frontend..."
docker build \
  -t "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:${IMAGE_TAG}" \
  -t "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:latest" \
  -f "${PROJECT_ROOT}/${FRONTEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/app"

docker push "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:${IMAGE_TAG}"
docker push "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:latest"

# ---------------------------------------------------------------------------
# Step 4: Create Azure Database for PostgreSQL Flexible Server
# ---------------------------------------------------------------------------
echo ">>> Step 4: Creating Azure Database for PostgreSQL..."
PG_PASSWORD=$(openssl rand -base64 32 | tr -d '/@"' | head -c 32)

if ! az postgres flexible-server show --name "${PG_SERVER}" --resource-group "${RESOURCE_GROUP}" 2>/dev/null; then
  az postgres flexible-server create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER}" \
    --location "${LOCATION}" \
    --admin-user "${PG_ADMIN}" \
    --admin-password "${PG_PASSWORD}" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --storage-size 32 \
    --version 15 \
    --public-access 0.0.0.0 \
    --tags app=finmind \
    --output none

  az postgres flexible-server db create \
    --resource-group "${RESOURCE_GROUP}" \
    --server-name "${PG_SERVER}" \
    --database-name "${PG_DB}" \
    --output none

  PG_FQDN=$(az postgres flexible-server show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER}" \
    --query fullyQualifiedDomainName --output tsv)

  DATABASE_URL="postgresql://${PG_ADMIN}:${PG_PASSWORD}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"
  echo "  PostgreSQL created: ${PG_FQDN}"
else
  PG_FQDN=$(az postgres flexible-server show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER}" \
    --query fullyQualifiedDomainName --output tsv)
  DATABASE_URL="postgresql://${PG_ADMIN}:EXISTING_PASSWORD@${PG_FQDN}:5432/${PG_DB}?sslmode=require"
  echo "  PostgreSQL already exists: ${PG_FQDN}"
fi

# ---------------------------------------------------------------------------
# Step 5: Create Azure Cache for Redis
# ---------------------------------------------------------------------------
echo ">>> Step 5: Creating Azure Cache for Redis..."
if ! az redis show --name "${REDIS_NAME}" --resource-group "${RESOURCE_GROUP}" 2>/dev/null; then
  az redis create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${REDIS_NAME}" \
    --location "${LOCATION}" \
    --sku Basic \
    --vm-size c0 \
    --tags app=finmind \
    --output none

  echo "  Waiting for Redis to provision (this may take several minutes)..."
  az redis wait --name "${REDIS_NAME}" --resource-group "${RESOURCE_GROUP}" --created
fi

REDIS_HOST=$(az redis show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${REDIS_NAME}" \
  --query hostName --output tsv)
REDIS_KEY=$(az redis list-keys \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${REDIS_NAME}" \
  --query primaryKey --output tsv)
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"
echo "  Redis: ${REDIS_HOST}"

# ---------------------------------------------------------------------------
# Step 6: Create Container Apps environment
# ---------------------------------------------------------------------------
echo ">>> Step 6: Creating Container Apps environment..."
LOG_WORKSPACE=$(az monitor log-analytics workspace create \
  --resource-group "${RESOURCE_GROUP}" \
  --workspace-name "${PROJECT_NAME}-logs" \
  --location "${LOCATION}" \
  --query customerId --output tsv 2>/dev/null)

LOG_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "${RESOURCE_GROUP}" \
  --workspace-name "${PROJECT_NAME}-logs" \
  --query primarySharedKey --output tsv)

az containerapp env create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ENVIRONMENT_NAME}" \
  --location "${LOCATION}" \
  --logs-workspace-id "${LOG_WORKSPACE}" \
  --logs-workspace-key "${LOG_KEY}" \
  --output none 2>/dev/null || echo "  Environment already exists."

echo "  Container Apps environment: ${ENVIRONMENT_NAME}"

# ---------------------------------------------------------------------------
# Step 7: Deploy backend Container App
# ---------------------------------------------------------------------------
echo ">>> Step 7: Deploying backend Container App..."

ACR_USERNAME=$(az acr credential show --name "${ACR_NAME}" --query username --output tsv)
ACR_PASSWORD=$(az acr credential show --name "${ACR_NAME}" --query 'passwords[0].value' --output tsv)

JWT_SECRET=$(openssl rand -base64 64)

az containerapp create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${BACKEND_APP}" \
  --environment "${ENVIRONMENT_NAME}" \
  --image "${ACR_LOGIN_SERVER}/${BACKEND_APP}:${IMAGE_TAG}" \
  --registry-server "${ACR_LOGIN_SERVER}" \
  --registry-username "${ACR_USERNAME}" \
  --registry-password "${ACR_PASSWORD}" \
  --target-port 8000 \
  --ingress external \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 10 \
  --env-vars \
    "DATABASE_URL=${DATABASE_URL}" \
    "REDIS_URL=${REDIS_URL}" \
    "JWT_SECRET=${JWT_SECRET}" \
    "GEMINI_API_KEY=${GEMINI_API_KEY:-REPLACE_ME}" \
    "LOG_LEVEL=info" \
    "GEMINI_MODEL=gemini-pro" \
  --scale-rule-name http-scaling \
  --scale-rule-type http \
  --scale-rule-http-concurrency 50 \
  --tags app=finmind component=backend \
  --output none 2>/dev/null || \
az containerapp update \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${BACKEND_APP}" \
  --image "${ACR_LOGIN_SERVER}/${BACKEND_APP}:${IMAGE_TAG}" \
  --output none

BACKEND_URL=$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${BACKEND_APP}" \
  --query 'properties.configuration.ingress.fqdn' --output tsv)
echo "  Backend deployed: https://${BACKEND_URL}"

# ---------------------------------------------------------------------------
# Step 8: Deploy frontend Container App
# ---------------------------------------------------------------------------
echo ">>> Step 8: Deploying frontend Container App..."
az containerapp create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FRONTEND_APP}" \
  --environment "${ENVIRONMENT_NAME}" \
  --image "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:${IMAGE_TAG}" \
  --registry-server "${ACR_LOGIN_SERVER}" \
  --registry-username "${ACR_USERNAME}" \
  --registry-password "${ACR_PASSWORD}" \
  --target-port 80 \
  --ingress external \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 0 \
  --max-replicas 5 \
  --env-vars "VITE_API_URL=https://${BACKEND_URL}" \
  --scale-rule-name http-scaling \
  --scale-rule-type http \
  --scale-rule-http-concurrency 100 \
  --tags app=finmind component=frontend \
  --output none 2>/dev/null || \
az containerapp update \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FRONTEND_APP}" \
  --image "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:${IMAGE_TAG}" \
  --output none

FRONTEND_URL=$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FRONTEND_APP}" \
  --query 'properties.configuration.ingress.fqdn' --output tsv)
echo "  Frontend deployed: https://${FRONTEND_URL}"

# ---------------------------------------------------------------------------
# Step 9: Verify health
# ---------------------------------------------------------------------------
echo ">>> Step 9: Verifying deployment..."
sleep 10
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${BACKEND_URL}/health" || echo "000")
if [[ "${HTTP_STATUS}" == "200" ]]; then
  echo "  Backend health check: PASSED (HTTP ${HTTP_STATUS})"
else
  echo "  Backend health check: FAILED (HTTP ${HTTP_STATUS})"
  echo "  Check logs: az containerapp logs show -n ${BACKEND_APP} -g ${RESOURCE_GROUP}"
fi

echo ""
echo "=== Deployment Complete ==="
echo "Backend:  https://${BACKEND_URL}"
echo "Frontend: https://${FRONTEND_URL}"
echo ""
echo "Useful commands:"
echo "  az containerapp logs show -n ${BACKEND_APP} -g ${RESOURCE_GROUP} --follow"
echo "  az containerapp revision list -n ${BACKEND_APP} -g ${RESOURCE_GROUP} -o table"
echo "  az containerapp show -n ${BACKEND_APP} -g ${RESOURCE_GROUP}"
