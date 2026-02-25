# FinMind — Netlify Deployment (Frontend)

## Quick Deploy

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind)

## Manual Deploy

```bash
# Install Netlify CLI
npm i -g netlify-cli

# Deploy
cd app
netlify deploy --prod

# Or connect Git repo for auto-deploy
netlify init
```

## Configuration

Set the `VITE_API_URL` environment variable in Netlify to point to your backend URL.

Config file: `deploy/netlify/netlify.toml`

### Features
- Auto-build from `app/` directory
- SPA fallback (all routes → `index.html`)
- Asset caching headers
- Build command: `npm run build`
- Publish directory: `app/dist`

> ⚠️ Netlify only hosts the frontend. You need a separate backend deployment (Fly.io, Railway, Render, etc.)
