# Deploy FinMind to Azure Container Apps

## Prerequisites
- Azure CLI installed and logged in
- Azure Database for PostgreSQL Flexible Server
- Azure Cache for Redis

## Deploy
```bash
# Set secrets
export JWT_SECRET=$(openssl rand -hex 32)
export DATABASE_URL="postgresql+psycopg2://finmind:password@your-server.postgres.database.azure.com:5432/finmind"
export REDIS_URL="rediss://your-redis.redis.cache.windows.net:6380"

# Run deployment
bash deploy/platforms/azure-container-apps/deploy.sh
```
