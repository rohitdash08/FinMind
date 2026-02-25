# FinMind — Heroku Deployment

## Quick Deploy

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)

## Manual Deploy

```bash
# 1. Create app
heroku create finmind-app
heroku stack:set container

# 2. Add databases
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# 3. Set secrets
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set GEMINI_API_KEY=your-key  # optional

# 4. Deploy
cp deploy/heroku/heroku.yml .
git push heroku main
```

## Review Apps

Enable in Heroku Pipeline. Configured via `deploy/heroku/app.json` with auto-provisioned PostgreSQL + Redis.

## Files

| File | Description |
|------|-------------|
| `app.json` | Heroku app manifest (review apps, env vars, addons) |
| `heroku.yml` | Container deployment config |
