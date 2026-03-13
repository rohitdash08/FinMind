# Render Deployment Guide

## Prerequisites
- GitHub repo connected to [Render](https://render.com)

## Blueprint Deploy (Recommended)

1. Go to [Render Blueprints](https://dashboard.render.com/blueprints)
2. Click **New Blueprint Instance**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and creates all services

The blueprint provisions:
- **Backend** — Docker web service on port 8000
- **Frontend** — Static site from `app/dist`
- **PostgreSQL** — Managed database
- **Redis** — Managed Redis instance

## Manual Deploy

### Backend
1. **New Web Service** → Docker → set Dockerfile path to `packages/backend/Dockerfile`
2. Set environment variables:
   - `DATABASE_URL` — from Render PostgreSQL
   - `REDIS_URL` — from Render Redis
   - `JWT_SECRET` — auto-generated
3. Set start command: `sh -c 'python -m flask --app wsgi:app init-db && gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app'`
4. Set health check path: `/health`

### Frontend
1. **New Static Site** → set build command: `cd app && npm ci && npm run build`
2. Set publish directory: `app/dist`
3. Add rewrite rule: `/* → /index.html` (SPA support)
4. Set `VITE_API_URL` to backend URL

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
