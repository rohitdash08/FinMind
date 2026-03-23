# DigitalOcean App Platform Deployment Guide
#
# Quick Start:
#   1. Install doctl: https://docs.digitalocean.com/reference/doctl/how-to/install/
#   2. Authenticate: doctl auth init
#   3. Deploy:
#        doctl apps create --spec deploy/paas/digitalocean/do-app.yaml
#   4. Update existing app:
#        doctl apps update <app-id> --spec deploy/paas/digitalocean/do-app.yaml
#
# Notes:
#   - Update the github.repo field if your fork has a different path
#   - Set real values for JWT_SECRET and GEMINI_API_KEY in the DO dashboard
#   - DATABASE_URL and REDIS_URL are auto-configured from managed databases
#   - The spec deploys both backend and frontend as separate services
#   - Managed Postgres and Redis are included in the spec
