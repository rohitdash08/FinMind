# Azure Container Apps Deployment Guide

## Prerequisites
- Azure CLI installed and logged in (`az login`)
- A resource group (`az group create --name finmind-rg --location eastus`)
- Azure Container Registry (ACR) with built images
- Azure Database for PostgreSQL flexible server
- Azure Cache for Redis

## Steps

1. **Create ACR and push images:**
   ```bash
   az acr create --resource-group finmind-rg --name finmindacr --sku Basic
   az acr login --name finmindacr

   docker build -t finmindacr.azurecr.io/finmind-backend -f packages/backend/Dockerfile packages/backend
   docker push finmindacr.azurecr.io/finmind-backend

   docker build -t finmindacr.azurecr.io/finmind-frontend -f app/Dockerfile app
   docker push finmindacr.azurecr.io/finmind-frontend
   ```

2. **Deploy with Bicep:**
   ```bash
   az deployment group create \
     --resource-group finmind-rg \
     --template-file deploy/azure/main.bicep \
     --parameters \
       backendImage=finmindacr.azurecr.io/finmind-backend:latest \
       frontendImage=finmindacr.azurecr.io/finmind-frontend:latest \
       databaseUrl='postgresql+psycopg2://user:pass@pg-host:5432/finmind' \
       redisUrl='redis://redis-host:6380?ssl=true' \
       jwtSecret=$(openssl rand -hex 32)
   ```

3. **Get endpoints:**
   ```bash
   az containerapp show --name finmind-backend --resource-group finmind-rg --query properties.configuration.ingress.fqdn
   az containerapp show --name finmind-frontend --resource-group finmind-rg --query properties.configuration.ingress.fqdn
   ```

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200 on backend FQDN
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
