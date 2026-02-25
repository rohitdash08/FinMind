# FinMind — Azure Container Apps Deployment

## Overview

Deploys FinMind to Azure Container Apps with:
- Container Apps for backend + frontend (auto-scaling)
- Azure Database for PostgreSQL Flexible Server
- Azure Cache for Redis
- Azure Container Registry (ACR)
- Log Analytics workspace
- Bicep IaC template

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- An Azure subscription
- Docker installed

## Quick Deploy

```bash
chmod +x deploy/azure/deploy.sh
./deploy/azure/deploy.sh
```

## Deploy with Bicep (IaC)

If you already have PostgreSQL and Redis provisioned:

```bash
az group create --name finmind-rg --location eastus

az deployment group create \
  --resource-group finmind-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    backendImage='ghcr.io/rohitdash08/finmind-backend:latest' \
    frontendImage='ghcr.io/rohitdash08/finmind-frontend:latest' \
    jwtSecret='YOUR_SECRET' \
    databaseUrl='postgresql://...' \
    redisUrl='redis://...'
```

## Deploy with Docker Compose Mode

```bash
az containerapp compose create \
  --resource-group finmind-rg \
  --environment finmind-env \
  --compose-file-path deploy/azure/azure-deploy.yaml
```

## Files

| File | Description |
|------|-------------|
| `deploy.sh` | Full automated deploy (ACR + PostgreSQL + Redis + Container Apps) |
| `bicep/main.bicep` | Bicep IaC template (Container Apps + Log Analytics) |
| `azure-deploy.yaml` | Docker Compose-compatible deployment |

## Cost Estimate

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| Container Apps (2 apps) | ~$0–20 (scale to zero) |
| PostgreSQL Flexible B1ms | ~$13 |
| Redis Basic C0 | ~$16 |
| Log Analytics | ~$2 |
| **Total** | **~$31–51/mo** |
