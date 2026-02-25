# FinMind — Fly.io Deployment

## Overview

Deploys FinMind backend + frontend as separate Fly.io apps with:
- Rolling deployments
- Auto-scaling (scale to zero)
- Built-in health checks
- HTTPS forced
- Free PostgreSQL and Redis via Fly addons

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed
- Fly.io account (`fly auth login`)

## Quick Deploy

```bash
chmod +x deploy/fly/deploy.sh
./deploy/fly/deploy.sh
```

## Manual Deploy

### 1. Create PostgreSQL & Redis

```bash
fly postgres create --name finmind-db --region sjc
fly redis create --name finmind-redis --region sjc
```

### 2. Deploy Backend

```bash
fly launch --name finmind-backend --config deploy/fly/fly.toml --no-deploy
fly secrets set JWT_SECRET=$(openssl rand -hex 32)
fly secrets set DATABASE_URL="postgres://..."  # from step 1
fly secrets set REDIS_URL="redis://..."        # from step 1
fly deploy --config deploy/fly/fly.toml
```

### 3. Deploy Frontend

```bash
fly launch --name finmind-frontend --config deploy/fly/fly-frontend.toml --no-deploy
fly deploy --config deploy/fly/fly-frontend.toml
```

## Files

| File | Description |
|------|-------------|
| `deploy.sh` | Automated deploy script |
| `fly.toml` | Backend Fly.io config |
| `fly-frontend.toml` | Frontend Fly.io config |

## Cost Estimate

Fly.io free tier includes 3 shared-cpu-1x VMs. Beyond that:

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| Backend (shared-cpu-1x) | ~$2–5 |
| Frontend (shared-cpu-1x) | ~$2–5 |
| PostgreSQL (1GB) | Free (dev) |
| Redis (25MB) | Free (Upstash) |
| **Total** | **~$4–10/mo** |
