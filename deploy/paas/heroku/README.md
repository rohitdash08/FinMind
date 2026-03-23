# Heroku Deployment Guide
#
# Quick Start:
#   1. Install the Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli
#   2. Copy deploy files to project root:
#        cp deploy/paas/heroku/heroku.yml .
#        cp deploy/paas/heroku/app.json .
#   3. Create the Heroku app:
#        heroku create finmind --stack container
#   4. Add addons:
#        heroku addons:create heroku-postgresql:essential-0
#        heroku addons:create heroku-redis:mini
#   5. Set secrets:
#        heroku config:set JWT_SECRET=$(openssl rand -hex 32)
#   6. Deploy:
#        git push heroku main
#
# Frontend:
#   Deploy as a separate Heroku app or use a static hosting service.
#   Set VITE_API_URL to your backend Heroku URL before building.
#
# Notes:
#   - Heroku auto-sets DATABASE_URL and REDIS_URL via addons
#   - The heroku.yml uses the Docker stack
#   - app.json enables "Deploy to Heroku" button and review apps
