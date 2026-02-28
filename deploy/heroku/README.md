# Heroku Deployment

## One-Click Deploy

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

## Manual Deployment

### Prerequisites
```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh
heroku login
```

### 1. Create App
```bash
heroku create finmind-app
heroku stack:set container
```

### 2. Add Add-ons
```bash
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
```

### 3. Configure Environment
```bash
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set GEMINI_API_KEY=your_key
heroku config:set LOG_LEVEL=INFO
```

### 4. Deploy
```bash
# Using Container Registry
heroku container:push web
heroku container:release web

# Or using Git
git push heroku main
```

### 5. Initialize Database
```bash
heroku run python -m flask --app wsgi:app init-db
```

## Frontend Deployment

For the frontend, deploy to Heroku as a separate static app or use Vercel/Netlify.

### Using Heroku Static Buildpack
```bash
cd app
heroku create finmind-frontend
heroku buildpacks:set heroku/nodejs
git push heroku main
```

## Environment Variables

| Variable | Description | Auto-Set |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL URL | ✅ |
| `REDIS_URL` | Redis URL | ✅ |
| `JWT_SECRET` | JWT secret | ❌ |
| `GEMINI_API_KEY` | AI API key | ❌ |

## Pricing

- Eco Dynos: $5/month
- PostgreSQL Essential: $5/month
- Redis Mini: $3/month

## Logs & Monitoring
```bash
heroku logs --tail
heroku ps
heroku open
```
