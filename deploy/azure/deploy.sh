#!/bin/bash
set -euo pipefail

# FinMind - Azure Container Apps Deployment
RESOURCE_GROUP="${AZURE_RG:-finmind-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENV_NAME="finmind-env"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"

echo "🚀 Deploying FinMind to Azure Container Apps..."

# Create resource group
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

# Create Container Apps environment
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Create Azure Database for PostgreSQL
echo "🐘 Creating PostgreSQL..."
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
  --yes

PG_HOST=$(az postgres flexible-server show --name finmind-db --resource-group "$RESOURCE_GROUP" --query fullyQualifiedDomainName -o tsv)

# Create Azure Cache for Redis
echo "🔴 Creating Redis..."
az redis create \
  --name finmind-redis \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Basic \
  --vm-size c0

REDIS_HOST=$(az redis show --name finmind-redis --resource-group "$RESOURCE_GROUP" --query hostName -o tsv)
REDIS_KEY=$(az redis list-keys --name finmind-redis --resource-group "$RESOURCE_GROUP" --query primaryKey -o tsv)

# Create ACR and push images
echo "📦 Creating Container Registry..."
az acr create --name finmindacr --resource-group "$RESOURCE_GROUP" --sku Basic --admin-enabled true
az acr login --name finmindacr

docker build -t finmindacr.azurecr.io/api:latest -f packages/backend/Dockerfile .
docker push finmindacr.azurecr.io/api:latest

docker build -t finmindacr.azurecr.io/web:latest -f app/Dockerfile app/
docker push finmindacr.azurecr.io/web:latest

ACR_PASSWORD=$(az acr credential show --name finmindacr --query passwords[0].value -o tsv)

# Deploy backend
echo "🚀 Deploying backend..."
az containerapp create \
  --name finmind-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image finmindacr.azurecr.io/api:latest \
  --registry-server finmindacr.azurecr.io \
  --registry-username finmindacr \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    "DATABASE_URL=postgresql+psycopg2://finmind:${DB_PASSWORD}@${PG_HOST}:5432/finmind" \
    "REDIS_URL=rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0" \
    "JWT_SECRET=${JWT_SECRET}" \
    "LOG_LEVEL=INFO"

BACKEND_URL=$(az containerapp show --name finmind-api --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)

# Deploy frontend
echo "🚀 Deploying frontend..."
az containerapp create \
  --name finmind-web \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image finmindacr.azurecr.io/web:latest \
  --registry-server finmindacr.azurecr.io \
  --registry-username finmindacr \
  --registry-password "$ACR_PASSWORD" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3

FRONTEND_URL=$(az containerapp show --name finmind-web --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)

echo ""
echo "🎉 FinMind deployed!"
echo "   Frontend: https://$FRONTEND_URL"
echo "   Backend:  https://$BACKEND_URL"
echo "   Health:   https://$BACKEND_URL/health"
