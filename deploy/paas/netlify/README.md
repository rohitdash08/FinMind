# Netlify Deployment Guide (Frontend)
#
# Quick Start:
#   1. Copy netlify.toml to project root: cp deploy/paas/netlify/netlify.toml .
#   2. Connect your repo on https://app.netlify.com
#   3. Set environment variables in Netlify dashboard:
#      - VITE_API_URL = your backend URL
#   4. Deploy!
#
# Notes:
#   - Only the frontend (app/) is deployed to Netlify
#   - SPA redirects are configured for React Router
#   - Static asset caching is enabled
#   - Deploy previews use development builds
#   - Deploy the backend separately (Railway, Render, Fly.io, etc.)
