# Railway Deployment Guide

## Prerequisites
- [Railway CLI](https://docs.railway.app/develop/cli) installed
- Railway account

## Steps

1. **Create project:**
   ```bash
   railway login
   railway init
   ```

2. **Add databases in the Railway dashboard:**
   - Click **+ New** → **Database** → **PostgreSQL**
   - Click **+ New** → **Database** → **Redis**

3. **Add backend service:**
   - Click **+ New** → **GitHub Repo** → select FinMind
   - Set **Root Directory** to `/packages/backend`
   - Railway auto-detects the Dockerfile
   - Add env vars: link `DATABASE_URL` and `REDIS_URL` from the database services
   - Set `JWT_SECRET`, `LOG_LEVEL=INFO`, `GEMINI_MODEL=gemini-1.5-flash`

4. **Add frontend service:**
   - Click **+ New** → **GitHub Repo** → select FinMind
   - Set **Root Directory** to `/app`
   - Set `VITE_API_URL` to the backend service URL

5. **Deploy:**
   ```bash
   railway up
   ```

## Configuration

See `deploy/railway/railway.json` for the backend service config. Railway uses this when the root directory is set to the repo root.

## Verification
1. Frontend loads at the Railway-provided URL
2. `GET /health` returns 200 on the backend URL
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
