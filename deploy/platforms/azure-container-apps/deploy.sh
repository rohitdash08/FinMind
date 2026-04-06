#!/bin/bash
set -euo pipefail

# FinMind - Azure Container Apps Deployment
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENV_NAME="finmind-env"

echo "=== Deploying FinMind to Azure Container Apps ==="

# Create resource group
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# Create Container Apps environment
az containerapp env create \
    --name "$ENV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION"

# Deploy backend
az containerapp create \
    --name finmind-backend \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENV_NAME" \
    --image ghcr.io/rohitdash08/finmind-backend:latest \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 10 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars LOG_LEVEL=INFO GEMINI_MODEL=gemini-1.5-flash \
    --secrets jwt-secret=\"\$JWT_SECRET\" \
    --scale-rule-name http-rule \
    --scale-rule-type http \
    --scale-rule-http-concurrency 50

# Deploy frontend
az containerapp create \
    --name finmind-frontend \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENV_NAME" \
    --image ghcr.io/rohitdash08/finmind-frontend:latest \
    --target-port 80 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 5 \
    --cpu 0.25 --memory 0.5Gi

echo "Deployment complete!"
echo "Backend URL: $(az containerapp show --name finmind-backend -g $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)"
echo "Frontend URL: $(az containerapp show --name finmind-frontend -g $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)"
