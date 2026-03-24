#!/bin/bash
# FinMind Frontend - Netlify Deployment
set -euo pipefail
echo "🔷 Deploying FinMind frontend to Netlify..."
cd ../../app && npm ci && npm run build
npx netlify-cli deploy --dir=dist --prod --site=${NETLIFY_SITE_ID}
echo "✅ Frontend deployed to Netlify!"
