#!/bin/bash
# FinMind - DigitalOcean App Platform Deployment  
set -euo pipefail
echo "🌊 Deploying FinMind to DigitalOcean..."
doctl apps create --spec deploy/scripts/do-app-spec.yaml
echo "✅ Deployed to DigitalOcean App Platform!"
