# Deploy FinMind to Fly.io

## Prerequisites
```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh
fly auth login
```

## Deploy
```bash
# Create Postgres
fly postgres create --name finmind-db --region iad

# Create Redis
fly redis create --name finmind-redis --region iad

# Deploy backend
fly launch --config deploy/platforms/flyio/fly.toml --no-deploy
fly secrets set JWT_SECRET=$(openssl rand -hex 32)
fly secrets set DATABASE_URL=$(fly postgres connection-string finmind-db)
fly secrets set REDIS_URL=$(fly redis connection-string finmind-redis)
fly deploy --config deploy/platforms/flyio/fly.toml

# Deploy frontend
fly launch --config deploy/platforms/flyio/fly-frontend.toml
fly deploy --config deploy/platforms/flyio/fly-frontend.toml
```
