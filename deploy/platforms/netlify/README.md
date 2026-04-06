# Deploy FinMind Frontend to Netlify

## One-Click Deploy
[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind)

## Setup
1. Connect your GitHub repo to Netlify
2. Set build settings:
   - Base directory: `app/`
   - Build command: `npm ci && npm run build`
   - Publish directory: `app/dist`
3. Set environment variable `VITE_API_URL` to your backend URL

## Notes
- This deploys only the frontend (React/Vite SPA)
- Backend must be deployed separately (see other platform guides)
- Netlify handles CDN, HTTPS, and redirects automatically
