# Render Deployment

## One-Click Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)

## What Gets Deployed

- **finmind-backend**: Flask API with Gunicorn
- **finmind-frontend**: Static React app
- **finmind-db**: PostgreSQL database
- **finmind-redis**: Redis cache

## Manual Setup

### 1. Create Services via Dashboard

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New Blueprint Instance"
3. Connect your FinMind fork
4. Select `deploy/render/render.yaml`

### 2. Configure Secrets

After deployment, add these environment variables to `finmind-backend`:

```
GEMINI_API_KEY=your_key_here
TWILIO_ACCOUNT_SID=optional
TWILIO_AUTH_TOKEN=optional
```

## Environment Variables

| Variable | Description | Auto-Generated |
|----------|-------------|----------------|
| `DATABASE_URL` | PostgreSQL URL | ✅ |
| `REDIS_URL` | Redis URL | ✅ |
| `JWT_SECRET` | JWT secret | ✅ |
| `GEMINI_API_KEY` | AI API key | ❌ |
| `LOG_LEVEL` | Log level | ✅ (INFO) |

## Free Tier Limits

- Web Services: Spin down after 15 min inactivity
- PostgreSQL: 90 days, 256MB
- Redis: 25MB

## Health Monitoring

Render automatically monitors `/health` endpoint.
