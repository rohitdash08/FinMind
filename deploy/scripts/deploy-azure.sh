#!/bin/bash
# FinMind - Azure Container Apps Deployment
set -euo pipefail
RG="finmind-rg"
ENV="finmind-env"
echo "☁️ Deploying FinMind to Azure Container Apps..."
az group create --name $RG --location eastus
az containerapp env create --name $ENV --resource-group $RG --location eastus
az containerapp create --name finmind-backend --resource-group $RG --environment $ENV \
  --image finmind/backend:latest --target-port 8000 --ingress external
az containerapp create --name finmind-frontend --resource-group $RG --environment $ENV \
  --image finmind/frontend:latest --target-port 80 --ingress external
echo "✅ Deployed to Azure Container Apps!"
