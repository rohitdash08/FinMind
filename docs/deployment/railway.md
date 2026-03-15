# Railway Deployment Guide

## One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?template=https://github.com/rohitdash08/FinMind)

> **Note:** Railway doesn't support multi-service blueprints in a single config file.
> The deploy button creates the backend service. You'll add databases and frontend
> from the Railway dashboard.

## Step-by-Step Setup

### 1. Create Project

```bash
railway login
railway init
```

Or create a new project in the [Railway Dashboard](https://railway.app/dashboard).

### 2. Add Databases

In the Railway dashboard:
- Click **+ New** → **Database** → **PostgreSQL**
- Click **+ New** → **Database** → **Redis**

### 3. Add Backend Service

- Click **+ New** → **GitHub Repo** → select FinMind
- Railway auto-detects the Dockerfile at `packages/backend/Dockerfile`
- In the service **Settings**, set **Root Directory** to `/packages/backend`
- In **Variables**, add:
  - `DATABASE_URL` → click "Add Reference" → select the PostgreSQL service → `DATABASE_URL`
  - `REDIS_URL` → click "Add Reference" → select the Redis service → `REDIS_URL`
  - `JWT_SECRET` → generate a random value (e.g., `openssl rand -hex 32`)
  - `LOG_LEVEL` → `INFO`
  - `GEMINI_MODEL` → `gemini-1.5-flash`

> Railway provides `DATABASE_URL` as `postgres://...` — the backend auto-converts this to
> `postgresql+psycopg2://` at startup. No manual conversion needed.

### 4. Add Frontend Service

- Click **+ New** → **GitHub Repo** → select FinMind again
- Set **Root Directory** to `/app`
- Railway auto-detects the Dockerfile in `app/`
- In **Variables**, add:
  - `VITE_API_URL` → set to the backend service's public URL

### 5. Deploy

Railway deploys automatically on push, or manually:

```bash
railway up
```

## Configuration

The `deploy/railway/railway.json` configures the backend service with:
- Dockerfile-based build
- Health check at `/health`
- Dynamic `$PORT` binding (Railway assigns the port)
- Auto-restart on failure

## Verification
1. Frontend loads at the Railway-provided URL
2. `GET /health` returns 200 on the backend URL
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
