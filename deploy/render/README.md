# FinMind — Render Deployment

## Quick Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

## Manual Deploy

1. Fork the repo to your GitHub
2. Log in to [Render Dashboard](https://dashboard.render.com)
3. New → Blueprint → select your repo
4. Render auto-detects `deploy/render/render.yaml`
5. Fill in environment variables → Deploy

Or use the CLI:
```bash
render blueprint launch --file deploy/render/render.yaml
```

## Blueprint Spec

The `render.yaml` Blueprint creates:
- Backend web service (Docker, health check on `/health`)
- Frontend web service (Docker)
- PostgreSQL 16 database
- Redis 7 instance

All services are linked via Render's internal service references — no manual connection string setup needed.

## Files

| File | Description |
|------|-------------|
| `render.yaml` | Render Blueprint spec (services + databases) |
