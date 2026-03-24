#!/bin/bash
# FinMind Frontend - Vercel Deployment
set -euo pipefail
echo "▲ Deploying FinMind frontend to Vercel..."
cd ../../app && npx vercel --prod
echo "✅ Frontend deployed to Vercel!"
