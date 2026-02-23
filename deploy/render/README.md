# Deploy FinMind on Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

## One-Click Deploy

1. Click the button above
2. Connect your GitHub account
3. Render will auto-create: PostgreSQL, Redis, Backend API, Frontend
4. Wait for all services to deploy (~5 minutes)
5. Access your frontend URL

## Manual Deploy

### Using render.yaml (Blueprint)

```bash
# Fork the repo, then in Render Dashboard:
# 1. New → Blueprint
# 2. Connect your fork
# 3. Select branch: main
# Render reads deploy/render/render.yaml automatically
```

### Individual Services

1. **Database**: New → PostgreSQL → Plan: Starter
2. **Redis**: New → Redis → Plan: Starter
3. **Backend**: New → Web Service → Docker → Root: `/`, Dockerfile: `packages/backend/Dockerfile`
4. **Frontend**: New → Static Site → Root: `app`, Build: `npm ci && npm run build`, Publish: `dist`

## Verify

- Backend Health: `https://finmind-api.onrender.com/health`
- Frontend: `https://finmind-web.onrender.com`
