# Deploy FinMind to Heroku

## One-Click Deploy
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

## CLI Deploy
```bash
# Login
heroku login

# Create app
heroku create finmind-app

# Add addons
heroku addons:create heroku-postgresql:mini
heroku addons:create heroku-redis:mini

# Set config
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set LOG_LEVEL=INFO

# Deploy backend
heroku stack:set container
git push heroku main

# Initialize DB
heroku run python -m flask --app wsgi:app init-db
```

## Frontend
Deploy the frontend separately on Heroku or use Netlify/Vercel (see respective guides).
