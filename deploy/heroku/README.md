# Deploy FinMind on Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

## Manual Deployment

### Backend

```bash
# Login
heroku login

# Create app
heroku create finmind-api

# Add addons
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# Set config
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set LOG_LEVEL=INFO

# Deploy backend
git subtree push --prefix packages/backend heroku main

# Or use Docker
heroku container:push web --context-path . --dockerfile packages/backend/Dockerfile
heroku container:release web

# Initialize database
heroku run python -m flask --app wsgi:app init-db
```

### Frontend

```bash
# Create separate app for frontend
heroku create finmind-web

# Set API URL
heroku config:set VITE_API_URL=https://finmind-api.herokuapp.com -a finmind-web

# Deploy frontend (use buildpack)
heroku buildpacks:set heroku/nodejs -a finmind-web
cd app && git subtree push --prefix app heroku-frontend main
```

### Verify

- Backend: `https://finmind-api.herokuapp.com/health`
- Frontend: `https://finmind-web.herokuapp.com`
