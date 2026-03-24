#!/bin/bash
# FinMind - Railway Deployment
set -euo pipefail
echo "🚂 Deploying FinMind to Railway..."
railway login
railway init --name finmind
railway add --plugin postgresql
railway add --plugin redis
railway variables set SECRET_KEY=$(openssl rand -hex 32)
railway up --detach
echo "✅ Deployed! Run 'railway open' to view."
