# FinMind — Railway Deployment

## Quick Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template?template=https://github.com/rohitdash08/FinMind)

## Manual Deploy

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login and init
railway login
railway init

# 3. Add PostgreSQL and Redis
railway add --plugin postgresql
railway add --plugin redis

# 4. Set environment variables
railway variables set JWT_SECRET=$(openssl rand -hex 32)
railway variables set GEMINI_API_KEY=your-key  # optional

# 5. Deploy
railway up
```

## Config

Config file: `deploy/railway/railway.toml`

Railway auto-detects the Dockerfile and sets up the backend service. Add a second service for the frontend pointing to `app/Dockerfile`.

## Features
- Auto-deploy on push
- Managed PostgreSQL + Redis plugins
- Health check on `/health`
- Auto-restart on failure (max 3 retries)
