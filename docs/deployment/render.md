# Render Deployment Guide

## One-Click Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

This creates all services automatically from `render.yaml`.

## Blueprint Deploy (Manual)

1. Go to [Render Blueprints](https://dashboard.render.com/blueprints)
2. Click **New Blueprint Instance**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and creates all services

The blueprint provisions:
- **Backend** — Docker web service on port 8000
- **Frontend** — Static site from `app/dist`
- **PostgreSQL** — Managed database (starter plan)
- **Redis** — Managed key-value store (starter plan)

## Post-Deploy Setup

1. After the first deploy, copy the backend service URL (e.g., `https://finmind-backend.onrender.com`)
2. Go to the **finmind-frontend** service → Environment → set `VITE_API_URL` to the backend URL
3. Trigger a manual deploy on the frontend to rebuild with the correct API URL

## Manual Deploy (Without Blueprint)

### Backend
1. **New Web Service** → Docker → set Dockerfile path to `packages/backend/Dockerfile`
2. Set environment variables:
   - `DATABASE_URL` — from Render PostgreSQL
   - `REDIS_URL` — from Render Redis (Key-Value Store)
   - `JWT_SECRET` — use "Generate" for a random value
3. Start command: `sh -c 'python -m flask --app wsgi:app init-db && gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app'`
4. Health check path: `/health`

### Frontend
1. **New Static Site** → set build command: `cd app && npm ci && npm run build`
2. Publish directory: `app/dist`
3. Add rewrite rule: `/* → /index.html` (SPA support)
4. Set `VITE_API_URL` to backend URL in environment variables

### Database
1. **New PostgreSQL** → starter plan

### Redis
1. **New Key-Value Store** (Redis) → starter plan
2. Copy the connection string → set as `REDIS_URL` on the backend

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
