# Azure Deployment

## Azure Container Apps (Recommended)

### Prerequisites
```bash
az login
az extension add --name containerapp
```

### 1. Create Resource Group and Environment
```bash
az group create --name finmind-rg --location eastus

az containerapp env create \
  --name finmind-env \
  --resource-group finmind-rg \
  --location eastus
```

### 2. Create Azure Container Registry
```bash
az acr create --name finmindregistry --resource-group finmind-rg --sku Basic
az acr login --name finmindregistry
```

### 3. Build and Push Image
```bash
cd packages/backend
az acr build --registry finmindregistry --image finmind-backend:latest .
```

### 4. Create PostgreSQL
```bash
az postgres flexible-server create \
  --name finmind-db \
  --resource-group finmind-rg \
  --admin-user finmind \
  --admin-password YOUR_PASSWORD \
  --sku-name Standard_B1ms \
  --tier Burstable
```

### 5. Create Redis Cache
```bash
az redis create \
  --name finmind-redis \
  --resource-group finmind-rg \
  --location eastus \
  --sku Basic \
  --vm-size C0
```

### 6. Deploy Container App
```bash
az containerapp create \
  --name finmind-backend \
  --resource-group finmind-rg \
  --environment finmind-env \
  --image finmindregistry.azurecr.io/finmind-backend:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server finmindregistry.azurecr.io \
  --secrets database-url=postgresql://... redis-url=redis://... jwt-secret=xxx \
  --env-vars DATABASE_URL=secretref:database-url REDIS_URL=secretref:redis-url JWT_SECRET=secretref:jwt-secret
```

## Frontend (Azure Static Web Apps)

```bash
cd app
az staticwebapp create \
  --name finmind-frontend \
  --resource-group finmind-rg \
  --source https://github.com/rohitdash08/FinMind \
  --location eastus \
  --branch main \
  --app-location "/app" \
  --output-location "dist"
```

## Cost Estimate

- Container Apps: ~$0-20/month (scale to zero)
- PostgreSQL Burstable B1ms: ~$15/month
- Redis Basic C0: ~$16/month
- Static Web Apps: Free tier
