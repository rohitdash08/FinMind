# Vercel Deployment Guide (Frontend)
#
# Quick Start:
#   1. Copy vercel.json to project root: cp deploy/paas/vercel/vercel.json .
#   2. Install Vercel CLI: npm i -g vercel
#   3. Set environment variables:
#        vercel env add VITE_API_URL  (set to your backend URL)
#   4. Deploy:
#        vercel --prod
#
# Or connect via Vercel Dashboard:
#   1. Import project on https://vercel.com/new
#   2. Set root directory to "app" (or use the vercel.json config)
#   3. Add VITE_API_URL environment variable
#   4. Deploy
#
# Notes:
#   - Only the frontend (app/) is deployed to Vercel
#   - SPA fallback routes are configured
#   - Static asset caching is enabled
#   - Deploy the backend separately
