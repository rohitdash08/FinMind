# FinMind Universal Deployment

One-click deploy FinMind to any major cloud platform.

## Supported Platforms

| Platform | Type | File | Deploy Command |
|----------|------|------|---------------|
| **Docker Compose** | Local dev | `docker-compose.yml` | `docker compose up --build` |
| **Kubernetes (k8s)** | Production | `deploy/k8s/` | `kubectl apply -f deploy/k8s/` |
| **Tilt** | Dev workflow | `deploy/tilt/Tiltfile` | `tilt up` |
| **Railway** | PaaS | `railway.json` | `railway up` |
| **Heroku** | PaaS | `Procfile`, `heroku.yml` | `git push heroku main` |
| **DigitalOcean App Platform** | PaaS | `deploy/digitalocean/app.yaml` | `doctl app create` |
| **Render** | PaaS | `deploy/render/render.yaml` | Connect repo via Render dashboard |
| **Fly.io** | PaaS | `fly.toml` | `fly launch` |
| **AWS ECS Fargate** | Container | `deploy/aws/` | `sh deploy/aws/deploy.sh` |
| **GCP Cloud Run** | Serverless | `deploy/gcp/` | `sh deploy/gcp/deploy-cloudrun.sh` |
| **Azure Container Instances** | Container | `deploy/azure/` | `sh deploy/azure/deploy.sh` |

## Quick Deploy

### Railway
```bash
railway login
railway up
```

### Heroku
```bash
heroku create finmind-api
git push heroku main
heroku open
```

### DigitalOcean
```bash
doctl apps create --spec deploy/digitalocean/app.yaml
```

### Render
Connect your GitHub repo at https://dashboard.render.com and use `deploy/render/render.yaml`.

### Fly.io
```bash
fly launch --copy-config --no-deploy
fly deploy
```

### AWS ECS
```bash
export REPO_URI=<ecr-repo-uri>
sh deploy/aws/deploy.sh
```

### GCP Cloud Run
```bash
export GCP_PROJECT_ID=your-project
sh deploy/gcp/deploy-cloudrun.sh
```

### Azure Container Instances
```bash
sh deploy/azure/deploy.sh
```

## Environment Variables

All platforms require these env vars (set in platform dashboard or CLI):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Secret for JWT token signing |
| `GEMINI_API_KEY` | (Optional) Google Gemini API key |
| `LOG_LEVEL` | Log level (default: INFO) |
