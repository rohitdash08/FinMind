# Heroku Deployment Guide

## One-Click Deploy

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

This uses `app.json` at the repo root to provision PostgreSQL, Redis, and set environment variables automatically.

## Manual CLI Deploy

```bash
# Create app
heroku create finmind-app
heroku stack:set container -a finmind-app

# Add add-ons (sets DATABASE_URL and REDIS_URL automatically)
heroku addons:create heroku-postgresql:essential-0 -a finmind-app
heroku addons:create heroku-redis:mini -a finmind-app

# Set secrets
heroku config:set JWT_SECRET=$(openssl rand -hex 32) -a finmind-app
heroku config:set LOG_LEVEL=INFO GEMINI_MODEL=gemini-1.5-flash -a finmind-app

# Deploy (uses heroku.yml at repo root)
git push heroku main
```

## Notes

- `heroku.yml` and `app.json` must be at the repo root for Heroku to detect them.
- The backend runs via the container stack using `packages/backend/Dockerfile`.
- Frontend should be deployed separately to Netlify/Vercel (Heroku is backend-only in this setup).
- Heroku auto-sets `DATABASE_URL` and `REDIS_URL` from add-ons.
- The `$PORT` variable is set by Heroku — gunicorn binds to it automatically.

## Verification
1. `heroku open -a finmind-app` — should show the app
2. `curl https://finmind-app.herokuapp.com/health` — returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
