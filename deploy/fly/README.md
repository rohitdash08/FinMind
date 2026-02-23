# Deploy FinMind on Fly.io

## Quick Deploy

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh
fly auth login

# Deploy everything
chmod +x deploy/fly/deploy.sh
./deploy/fly/deploy.sh
```

## Manual Deploy

### 1. Create Apps & Infrastructure

```bash
fly apps create finmind-api
fly postgres create --name finmind-db --region sjc
fly postgres attach finmind-db --app finmind-api
fly redis create --name finmind-redis --region sjc
```

### 2. Set Secrets

```bash
fly secrets set \
  JWT_SECRET=$(openssl rand -hex 32) \
  REDIS_URL=redis://default:@finmind-redis.internal:6379 \
  LOG_LEVEL=INFO \
  --app finmind-api
```

### 3. Deploy Backend

```bash
fly deploy --config deploy/fly/fly.backend.toml --app finmind-api
```

### 4. Deploy Frontend

```bash
fly apps create finmind-web
fly deploy --config deploy/fly/fly.frontend.toml --app finmind-web \
  --build-arg VITE_API_URL=https://finmind-api.fly.dev
```

## Verify

- Frontend: `https://finmind-web.fly.dev`
- Backend: `https://finmind-api.fly.dev/health`
