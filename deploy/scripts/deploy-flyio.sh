#!/bin/bash
# FinMind - Fly.io Deployment
set -euo pipefail
echo "🪰 Deploying FinMind to Fly.io..."
fly launch --name finmind --region iad --no-deploy
fly postgres create --name finmind-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x
fly postgres attach finmind-db
fly redis create --name finmind-redis --region iad --no-replicas
fly secrets set SECRET_KEY=$(openssl rand -hex 32)
fly deploy
echo "✅ Deployed! Visit: https://finmind.fly.dev"
