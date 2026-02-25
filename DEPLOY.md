# FinMind — Universal Deployment Guide

Deploy FinMind anywhere with one click or one command.

## 🚀 Quick Deploy Buttons

| Platform | Deploy |
|----------|--------|
| **Heroku** | [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind) |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template?template=https://github.com/rohitdash08/FinMind) |
| **Netlify** (frontend) | [![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind) |
| **Vercel** (frontend) | [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app) |
| **DigitalOcean** | [![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main) |

## 📋 All Deployment Options

### PaaS (Managed Platforms)

| Platform | Type | Guide | Difficulty | One-Click |
|----------|------|-------|------------|-----------|
| [Railway](deploy/railway/) | Full stack | [README](deploy/railway/README.md) | 🟢 Easy | ✅ |
| [Heroku](deploy/heroku/) | Full stack | [README](deploy/heroku/README.md) | 🟢 Easy | ✅ |
| [Render](deploy/render/) | Full stack | [README](deploy/render/README.md) | 🟢 Easy | ✅ |
| [Fly.io](deploy/fly/) | Full stack | [README](deploy/fly/README.md) | 🟡 Medium | — |
| [DigitalOcean App Platform](deploy/digitalocean/) | Full stack | [README](deploy/digitalocean/README.md) | 🟢 Easy | ✅ |
| [DigitalOcean Droplet](deploy/digitalocean/) | Full stack | [README](deploy/digitalocean/README.md) | 🟡 Medium | — |

### Cloud Providers

| Platform | Type | Guide | Difficulty | IaC |
|----------|------|-------|------------|-----|
| [AWS ECS Fargate](deploy/aws/) | Full stack | [README](deploy/aws/README.md) | 🔴 Advanced | CloudFormation |
| [AWS App Runner](deploy/aws/) | Backend | [README](deploy/aws/README.md) | 🟡 Medium | YAML |
| [GCP Cloud Run](deploy/gcp/) | Full stack | [README](deploy/gcp/README.md) | 🟡 Medium | Cloud Build |
| [Azure Container Apps](deploy/azure/) | Full stack | [README](deploy/azure/README.md) | 🟡 Medium | Bicep |

### Kubernetes

| Platform | Type | Guide | Difficulty |
|----------|------|-------|------------|
| [Helm Charts](deploy/helm/) | Production K8s | [README](deploy/helm/README.md) | 🔴 Advanced |
| [Raw K8s Manifests](deploy/k8s/) | K8s | [README](deploy/k8s/README.md) | 🔴 Advanced |

### Frontend Only

| Platform | Guide | One-Click |
|----------|-------|-----------|
| [Netlify](deploy/netlify/) | [README](deploy/netlify/README.md) | ✅ |
| [Vercel](deploy/vercel/) | [README](deploy/vercel/README.md) | ✅ |

### Local Development

| Tool | Guide |
|------|-------|
| [Docker Compose](docker-compose.yml) | `docker compose up -d` |
| [Tilt (K8s dev)](Tiltfile) | [README](deploy/tilt/README.md) |

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL  │
│  React/Vite  │     │  Flask API   │     │     16       │
│  (Nginx)     │     │  (Gunicorn)  │     └─────────────┘
│  Port: 80    │     │  Port: 8000  │────▶┌─────────────┐
└─────────────┘     └─────────────┘     │    Redis 7   │
                                         └─────────────┘
```

### Monitoring Stack (included)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Prometheus  │────▶│   Grafana    │     │    Loki      │
│  Metrics     │     │  Dashboards  │◀────│  Log Agg.    │
└──────┬──────┘     └─────────────┘     └──────┬──────┘
       │                                        │
  ┌────┴────┐                              ┌────┴────┐
  │Exporters│                              │Promtail │
  │node/pg/ │                              │Log Ship │
  │redis/ngx│                              └─────────┘
  └─────────┘
```

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `JWT_SECRET` | ✅ | Secret for JWT token signing (≥32 chars) |
| `VITE_API_URL` | ✅ (frontend) | Backend API URL |
| `LOG_LEVEL` | ❌ | Logging level (default: INFO) |
| `GEMINI_API_KEY` | ❌ | Google Gemini API key for AI features |
| `GEMINI_MODEL` | ❌ | Gemini model (default: gemini-1.5-flash) |
| `OPENAI_API_KEY` | ❌ | OpenAI API key for AI features |

## ✅ Verification Checklist

After deploying, verify all acceptance criteria:

- [ ] Frontend loads at the configured URL
- [ ] Backend health check passes: `GET /health` returns 200
- [ ] Database connected (can create account)
- [ ] Redis connected (session/cache working)
- [ ] Auth flows working (register → login → JWT)
- [ ] Expenses module works
- [ ] Bills module works
- [ ] Reminders module works
- [ ] Dashboard shows data
- [ ] Insights/AI features work (if API keys configured)

## 📊 Monitoring (Docker Compose / K8s)

The full monitoring stack is included out of the box:

| Service | Port | Description |
|---------|------|-------------|
| Prometheus | 9090 | Metrics collection & alerting |
| Grafana | 3000 | Dashboards & visualization |
| Loki | 3100 | Log aggregation |
| Promtail | — | Log shipping agent |
| Node Exporter | 9100 | Host metrics |
| Postgres Exporter | 9187 | PostgreSQL metrics |
| Redis Exporter | 9121 | Redis metrics |
| Nginx Exporter | 9113 | Nginx metrics |

Default Grafana credentials: `finmind_admin` / `change-this-admin-password`
