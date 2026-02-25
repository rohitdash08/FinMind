# FinMind — Vercel Deployment (Frontend)

## Quick Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app)

## Manual Deploy

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd app
vercel --prod

# Or connect Git repo
vercel link
```

## Configuration

1. Set `VITE_API_URL` in Vercel project settings → Environment Variables
2. Update the API proxy URL in `deploy/vercel/vercel.json` if needed

Config file: `deploy/vercel/vercel.json`

### Features
- Auto-build from `app/` directory
- SPA rewrites (all routes → `index.html`)
- API proxy to backend (`/api/**` → backend URL)
- Build command: `npm run build`
- Output directory: `dist`

> ⚠️ Vercel only hosts the frontend. You need a separate backend deployment.
