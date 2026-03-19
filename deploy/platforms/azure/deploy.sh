#!/usr/bin/env bash
# FinMind - Azure Container Apps Deployment
# Prerequisites: az CLI logged in
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENVIRONMENT_NAME="${AZURE_ENV_NAME:-finmind-env}"
ACR_NAME="${AZURE_ACR_NAME:-finmindacr}"

echo "=== FinMind Azure Container Apps Deployment ==="

# Step 1: Create resource group
echo "Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# Step 2: Create ACR
echo "Creating Azure Container Registry..."
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true

# Step 3: Build and push images
echo "Building and pushing images..."
az acr build --registry "$ACR_NAME" --image finmind-backend:latest ./packages/backend
az acr build --registry "$ACR_NAME" --image finmind-frontend:latest ./app

# Step 4: Create Container Apps Environment
echo "Creating Container Apps environment..."
az containerapp env create \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION"

# Step 5: Deploy backend
echo "Deploying backend..."
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
az containerapp create \
    --name finmind-backend \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$ACR_NAME.azurecr.io/finmind-backend:latest" \
    --registry-server "$ACR_NAME.azurecr.io" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 10 \
    --cpu 0.5 \
    --memory 1Gi \
    --env-vars "GEMINI_MODEL=gemini-1.5-flash" "LOG_LEVEL=INFO"

# Step 6: Deploy frontend
echo "Deploying frontend..."
BACKEND_FQDN=$(az containerapp show --name finmind-backend --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
az containerapp create \
    --name finmind-frontend \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$ACR_NAME.azurecr.io/finmind-frontend:latest" \
    --registry-server "$ACR_NAME.azurecr.io" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 80 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 5 \
    --cpu 0.25 \
    --memory 0.5Gi \
    --env-vars "VITE_API_URL=https://$BACKEND_FQDN"

FRONTEND_FQDN=$(az containerapp show --name finmind-frontend --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "=== Deployment complete! ==="
echo "Backend:  https://$BACKEND_FQDN"
echo "Frontend: https://$FRONTEND_FQDN"
