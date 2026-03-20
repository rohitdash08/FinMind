# Fly.io Deployment Guide

## Prerequisites
- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed
- Fly.io account (`fly auth login`)

## Quick Deploy

Run the automated deploy script:
```bash
bash deploy/fly/deploy.sh
```

This will:
1. Create a Fly Postgres cluster (`finmind-db`)
2. Create a Fly Redis instance via Upstash (`finmind-redis`)
3. Deploy the backend from `packages/backend/` using `deploy/fly/fly.backend.toml`
4. Attach Postgres and set secrets
5. Deploy the frontend from `app/` using `deploy/fly/fly.frontend.toml`

## Manual Deploy

```bash
# Create Postgres
fly postgres create --name finmind-db --region iad

# Create Redis (via Upstash integration)
fly ext redis create --name finmind-redis --region iad

# Deploy backend (build context = packages/backend/)
fly deploy packages/backend --config deploy/fly/fly.backend.toml --remote-only
fly postgres attach finmind-db --app finmind-backend
fly secrets set --app finmind-backend JWT_SECRET=$(openssl rand -hex 32)
# Set REDIS_URL from the Upstash Redis dashboard or fly ext redis status

# Deploy frontend (build context = app/)
fly deploy app --config deploy/fly/fly.frontend.toml --remote-only
```

## Endpoints
- Backend: `https://finmind-backend.fly.dev/health`
- Frontend: `https://finmind-frontend.fly.dev`

## Scaling
```bash
fly scale count 2 --app finmind-backend  # add replicas
fly scale vm shared-cpu-2x --app finmind-backend  # bigger VM
```

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
