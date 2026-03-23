# Railway Deployment Guide
#
# FinMind deploys on Railway with managed Postgres and Redis.
#
# Quick Start:
#   1. Create a new project on https://railway.app
#   2. Add a PostgreSQL service and a Redis service from the Railway dashboard
#   3. Connect your GitHub repo
#   4. Copy railway.toml to the project root: cp deploy/paas/railway/railway.toml .
#   5. Set environment variables in Railway dashboard:
#      - DATABASE_URL        → auto-set by Railway Postgres plugin
#      - REDIS_URL           → auto-set by Railway Redis plugin
#      - JWT_SECRET          → your secret key
#      - POSTGRES_USER       → from Railway Postgres
#      - POSTGRES_PASSWORD   → from Railway Postgres
#      - POSTGRES_DB         → from Railway Postgres
#      - GEMINI_API_KEY      → (optional) for AI insights
#   6. Deploy!
#
# Frontend:
#   Deploy the app/ directory as a separate Railway service with:
#   - Build command: npm ci && npm run build
#   - Or use the Dockerfile at app/Dockerfile
#   - Set VITE_API_URL to your backend Railway URL
#
# Notes:
#   - Railway auto-detects the Dockerfile from railway.toml
#   - Health checks are configured at /health
#   - The start command runs init-db before starting gunicorn
