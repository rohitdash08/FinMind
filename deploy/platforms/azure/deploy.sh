#!/usr/bin/env bash
# FinMind — One-click Azure Container Apps deployment
# Prerequisites: az CLI authenticated, SUBSCRIPTION_ID + RESOURCE_GROUP set
# Usage: SUBSCRIPTION_ID=xxx RESOURCE_GROUP=finmind-rg LOCATION=eastus ./deploy.sh
set -euo pipefail

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:?Set SUBSCRIPTION_ID}"
RESOURCE_GROUP="${RESOURCE_GROUP:-finmind-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-finmindacr}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

az account set --subscription "$SUBSCRIPTION_ID"

# Create resource group
log "Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Create Container Apps Environment
log "Creating Container Apps environment..."
az containerapp env create \
  --name finmind-env \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# Deploy backend
log "Deploying backend container app..."
az containerapp create \
  --name finmind-backend \
  --resource-group "$RESOURCE_GROUP" \
  --environment finmind-env \
  --image "ghcr.io/rohitdash08/finmind-backend:${IMAGE_TAG}" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    "LOG_LEVEL=INFO" \
    "GEMINI_MODEL=gemini-1.5-flash" \
    "PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc" \
    "POSTGRES_USER=secretref:postgres-user" \
    "POSTGRES_PASSWORD=secretref:postgres-password" \
    "POSTGRES_DB=secretref:postgres-db" \
    "DATABASE_URL=secretref:database-url" \
    "REDIS_URL=secretref:redis-url" \
    "JWT_SECRET=secretref:jwt-secret" \
    "GEMINI_API_KEY=secretref:gemini-api-key" \
  --command "sh" "-c" \
    "python -m flask --app wsgi:app init-db && rm -rf \$PROMETHEUS_MULTIPROC_DIR && mkdir -p \$PROMETHEUS_MULTIPROC_DIR && exec gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app" \
  --output none

BACKEND_FQDN=$(az containerapp show --name finmind-backend --resource-group "$RESOURCE_GROUP" --query 'properties.configuration.ingress.fqdn' --output tsv)
log "Backend: https://$BACKEND_FQDN"

# Deploy frontend
log "Deploying frontend container app..."
az containerapp create \
  --name finmind-frontend \
  --resource-group "$RESOURCE_GROUP" \
  --environment finmind-env \
  --image "ghcr.io/rohitdash08/finmind-frontend:${IMAGE_TAG}" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars "VITE_API_URL=https://${BACKEND_FQDN}" \
  --output none

FRONTEND_FQDN=$(az containerapp show --name finmind-frontend --resource-group "$RESOURCE_GROUP" --query 'properties.configuration.ingress.fqdn' --output tsv)
log "Frontend: https://$FRONTEND_FQDN"
log "Deployment complete. Open: https://$FRONTEND_FQDN"
