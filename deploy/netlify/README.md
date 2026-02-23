# Deploy FinMind Frontend on Netlify

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind)

## Setup

1. Click Deploy button or connect repo in Netlify dashboard
2. Set build settings:
   - Base directory: `app`
   - Build command: `npm ci && npm run build`
   - Publish directory: `app/dist`
3. Set environment variable: `VITE_API_URL=https://your-backend-url`
4. Deploy

## Custom Domain

In Netlify dashboard → Domain Settings → Add custom domain
