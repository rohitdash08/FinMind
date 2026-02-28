# FinMind Deployment Configurations

This folder contains deployment configurations for all supported platforms.

## 📁 Structure

```
deploy/
├── railway/           # Railway one-click deploy
│   ├── railway.json
│   └── README.md
├── render/            # Render Blueprint
│   ├── render.yaml
│   └── README.md
├── fly/               # Fly.io deployment
│   ├── fly.toml
│   └── README.md
├── heroku/            # Heroku Container deployment
│   ├── heroku.yml
│   ├── app.json
│   └── README.md
├── digitalocean/      # DigitalOcean (App Platform + Droplet)
│   ├── .do/app.yaml
│   ├── droplet/setup.sh
│   └── README.md
├── aws/               # AWS (ECS Fargate + App Runner)
│   ├── ecs-task-definition.json
│   ├── apprunner.yaml
│   └── README.md
├── gcp/               # Google Cloud Run
│   ├── cloudrun.yaml
│   └── README.md
├── azure/             # Azure Container Apps
│   ├── container-app.yaml
│   └── README.md
├── helm/              # Kubernetes Helm chart
│   └── finmind/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── templates/
│       └── README.md
├── k8s/               # Raw Kubernetes manifests
│   ├── namespace.yaml
│   ├── app-stack.yaml
│   ├── secrets.example.yaml
│   └── monitoring-stack.yaml
├── tilt/              # Tilt local K8s development
│   └── README.md
├── nginx/             # Production Nginx config
│   └── nginx.prod.conf
├── vercel/            # Vercel frontend config
│   └── vercel.json
├── netlify/           # Netlify frontend config
│   └── netlify.toml
└── frontend/          # Frontend deployment guide
    └── README.md
```

## 🚀 Quick Reference

| Platform | Type | One-Click | Free Tier | Docs |
|----------|------|-----------|-----------|------|
| Railway | PaaS | ✅ | ✅ $5/mo | [README](railway/README.md) |
| Render | PaaS | ✅ | ✅ | [README](render/README.md) |
| Fly.io | PaaS | ❌ | ✅ | [README](fly/README.md) |
| Heroku | PaaS | ✅ | ❌ | [README](heroku/README.md) |
| DigitalOcean | PaaS/VPS | ✅ | ❌ | [README](digitalocean/README.md) |
| AWS | Cloud | ❌ | ❌ | [README](aws/README.md) |
| GCP | Cloud | ❌ | ✅ | [README](gcp/README.md) |
| Azure | Cloud | ❌ | ✅ | [README](azure/README.md) |
| Kubernetes | K8s | ❌ | N/A | [README](helm/README.md) |
| Tilt | Dev | ❌ | N/A | [README](tilt/README.md) |
| Vercel | Frontend | ✅ | ✅ | [README](frontend/README.md) |
| Netlify | Frontend | ✅ | ✅ | [README](frontend/README.md) |

## 💡 Recommended Setups

### Development / Hobby
- **Option 1**: Docker Compose locally
- **Option 2**: Railway free tier (backend) + Vercel (frontend)
- **Cost**: Free - $5/month

### Small Production
- **Option 1**: Render paid tier (full stack)
- **Option 2**: DigitalOcean Droplet ($12/mo)
- **Cost**: $12-25/month

### Production Scale
- **Backend**: Kubernetes (EKS/GKE/AKS) with Helm chart
- **Frontend**: Vercel/Cloudflare Pages
- **Cost**: $100+/month

### Enterprise
- **Full Stack**: Kubernetes with GitOps (ArgoCD/Flux)
- **Multi-region**: Cloud provider managed K8s
- **Cost**: $500+/month

## 🛠️ One-Command Deploy

Use the universal deployment script:

```bash
# From project root
./scripts/deploy.sh [platform]

# Examples:
./scripts/deploy.sh docker        # Docker Compose dev
./scripts/deploy.sh docker-prod   # Docker Compose production
./scripts/deploy.sh helm          # Kubernetes with Helm
./scripts/deploy.sh tilt          # Local K8s dev with Tilt
./scripts/deploy.sh fly           # Deploy to Fly.io
./scripts/deploy.sh railway       # Deploy to Railway
```

Windows:
```powershell
.\scripts\deploy.ps1 [platform]
```

## 📦 Docker Images

Pre-built images are available on GitHub Container Registry:

```bash
docker pull ghcr.io/rohitdash08/finmind-backend:latest
docker pull ghcr.io/rohitdash08/finmind-frontend:latest
```

## 🔒 Secrets Management

All deployments require these secrets:

| Secret | Required | Generate |
|--------|----------|----------|
| `JWT_SECRET` | ✅ | `openssl rand -hex 32` |
| `DATABASE_URL` | ✅ | Platform-provided |
| `REDIS_URL` | ✅ | Platform-provided |
| `GEMINI_API_KEY` | ❌ | Google AI Studio |

## 📊 Features by Platform

| Feature | Docker | K8s/Helm | Railway | Fly.io | Render |
|---------|--------|----------|---------|--------|--------|
| Auto-scaling | ❌ | ✅ | ✅ | ✅ | ✅ |
| SSL/TLS | Manual | ✅ | ✅ | ✅ | ✅ |
| CI/CD | GitHub Actions | GitOps | ✅ | ✅ | ✅ |
| Monitoring | ✅ | ✅ | Basic | ✅ | Basic |
| Logs | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cost | VPS cost | Variable | Pay-per-use | Pay-per-use | Pay-per-use |

## 📚 Additional Resources

- [Main Deployment Guide](../DEPLOYMENT.md)
- [Contributing](../CONTRIBUTING.md)
- [README](../README.md)
