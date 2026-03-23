# Fly.io Deployment Guide
#
# Quick Start:
#   1. Install flyctl: https://fly.io/docs/flyctl/install/
#   2. Authenticate: fly auth login
#   3. Copy fly.toml to project root: cp deploy/paas/flyio/fly.toml .
#   4. Create the app:
#        fly apps create finmind-backend
#   5. Create managed Postgres:
#        fly postgres create --name finmind-db
#        fly postgres attach finmind-db --app finmind-backend
#   6. Create managed Redis (Upstash):
#        fly redis create --name finmind-redis
#   7. Set secrets:
#        fly secrets set JWT_SECRET=$(openssl rand -hex 32)
#        fly secrets set REDIS_URL=<redis-url-from-step-6>
#        fly secrets set GEMINI_API_KEY=<your-key>
#   8. Deploy:
#        fly deploy
#
# Frontend:
#   Deploy as a separate Fly app using app/Dockerfile, or use
#   a static hosting platform (Netlify/Vercel).
#
# Notes:
#   - DATABASE_URL is auto-set when attaching Fly Postgres
#   - release_command runs init-db before each deploy
#   - Health checks and metrics collection are configured
#   - Auto-stop/start saves costs on low-traffic apps
