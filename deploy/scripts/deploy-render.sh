#!/bin/bash
# FinMind - Render Deployment
set -euo pipefail
echo "🎨 Deploying FinMind to Render..."
cat > render.yaml << 'YAML'
services:
  - type: web
    name: finmind-backend
    runtime: docker
    dockerfilePath: deploy/docker/Dockerfile.backend
    envVars:
      - key: DATABASE_URL
        fromDatabase: { name: finmind-db, property: connectionString }
      - key: REDIS_URL
        fromService: { name: finmind-redis, type: redis, property: connectionString }
  - type: web
    name: finmind-frontend
    runtime: static
    buildCommand: cd app && npm ci && npm run build
    staticPublishPath: app/dist
databases:
  - name: finmind-db
    plan: starter
YAML
echo "✅ render.yaml created! Push to GitHub and connect to Render Dashboard."
