#!/bin/bash
# FinMind - Heroku Deployment
set -euo pipefail
echo "🟣 Deploying FinMind to Heroku..."
heroku create finmind-app
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
heroku config:set SECRET_KEY=$(openssl rand -hex 32)
heroku container:push --recursive
heroku container:release web
echo "✅ Deployed! Visit: https://finmind-app.herokuapp.com"
