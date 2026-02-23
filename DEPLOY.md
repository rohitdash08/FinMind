# FinMind - Universal Deployment Guide

Deploy FinMind anywhere with one click or one command.

## 🚀 Quick Deploy Buttons

| Platform | Deploy |
|----------|--------|
| **Heroku** | [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind) |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind) |
| **Netlify** (frontend) | [![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind) |
| **Vercel** (frontend) | [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template) |

## 📋 All Deployment Options

### PaaS (Managed Platforms)

| Platform | Type | Guide | Difficulty |
|----------|------|-------|------------|
| [Railway](deploy/railway/) | Full stack | [README](deploy/railway/README.md) | ⭐ Easy |
| [Heroku](deploy/heroku/) | Full stack | [README](deploy/heroku/README.md) | ⭐ Easy |
| [Render](deploy/render/) | Full stack | [README](deploy/render/README.md) | ⭐ Easy |
| [Fly.io](deploy/fly/) | Full stack | [README](deploy/fly/README.md) | ⭐⭐ Medium |
| [DigitalOcean App Platform](deploy/digitalocean/app-platform/) | Full stack | [README](deploy/digitalocean/app-platform/README.md) | ⭐ Easy |
| [DigitalOcean Droplet](deploy/digitalocean/droplet/) | Full stack | [README](deploy/digitalocean/droplet/README.md) | ⭐⭐ Medium |

### Cloud Providers

| Platform | Type | Guide | Difficulty |
|----------|------|-------|------------|
| [AWS ECS Fargate](deploy/aws/ecs-fargate/) | Full stack | [README](deploy/aws/ecs-fargate/README.md) | ⭐⭐⭐ Advanced |
| [AWS App Runner](deploy/aws/app-runner/) | Backend | [README](deploy/aws/app-runner/README.md) | ⭐⭐ Medium |
| [GCP Cloud Run](deploy/gcp/) | Full stack | [README](deploy/gcp/README.md) | ⭐⭐ Medium |
| [Azure Container Apps](deploy/azure/) | Full stack | [README](deploy/azure/README.md) | ⭐⭐ Medium |

### Kubernetes

| Platform | Type | Guide | Difficulty |
|----------|------|-------|------------|
| [Helm Charts](deploy/helm/) | Production K8s | [README](deploy/helm/README.md) | ⭐⭐⭐ Advanced |
| [Raw K8s Manifests](deploy/k8s/) | K8s | [README](deploy/k8s/README.md) | ⭐⭐⭐ Advanced |

### Frontend Only

| Platform | Guide |
|----------|-------|
| [Netlify](deploy/netlify/) | [README](deploy/netlify/README.md) |
| [Vercel](deploy/vercel/) | [README](deploy/vercel/README.md) |

### Local Development

| Tool | Guide |
|------|-------|
| [Docker Compose](docker-compose.yml) | `docker compose up -d` |
| [Tilt (K8s dev)](Tiltfile) | [README](deploy/tilt/README.md) |

## 🏗 Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL  │
│  React/Vite  │     │  Flask API   │     │     16       │
│  (Nginx)     │     │  (Gunicorn)  │     └──────────────┘
│  Port: 80    │     │  Port: 8000  │────▶┌──────────────┐
└─────────────┘     └──────────────┘     │    Redis 7   │
                                          └──────────────┘
```

## ⚙️ Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `JWT_SECRET` | ✅ | Secret for JWT token signing |
| `VITE_API_URL` | ✅ (frontend) | Backend API URL |
| `LOG_LEVEL` | ❌ | Logging level (default: INFO) |
| `OPENAI_API_KEY` | ❌ | For AI features |
| `GEMINI_API_KEY` | ❌ | For AI features |

## ✅ Verification Checklist

After deploying, verify:

- [ ] Frontend loads at the configured URL
- [ ] Backend health check passes: `GET /health`
- [ ] Can create a new account (DB + Redis connected)
- [ ] Can log in (auth flows working)
- [ ] Expenses module works
- [ ] Bills module works
- [ ] Dashboard shows data
- [ ] Reminders work
- [ ] Insights/AI features work (if API keys configured)
