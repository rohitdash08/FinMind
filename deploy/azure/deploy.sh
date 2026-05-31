#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${AZURE_RG:-finmind}"
LOCATION="${AZURE_LOCATION:-eastus}"

echo "=== Deploying FinMind to Azure ==="

az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file arm-template.json \
  --parameters containerGroupName=finmind-backend

echo "Deployment complete. Container status:"
az container show --resource-group "$RESOURCE_GROUP" --name finmind-backend --query instanceViewState
