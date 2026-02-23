# Deploy FinMind on Azure Container Apps

## Quick Deploy

```bash
az login
chmod +x deploy/azure/deploy.sh
./deploy/azure/deploy.sh
```

## What Gets Created

- Resource Group
- Container Apps Environment
- Azure Database for PostgreSQL Flexible Server
- Azure Cache for Redis
- Azure Container Registry
- Container Apps (API + Frontend)

## Cleanup

```bash
az group delete --name finmind-rg --yes
```

## Cost

~$30-50/month (PostgreSQL Burstable B1ms + Redis Basic C0 + Container Apps)
