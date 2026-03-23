# FinMind — Deployment Configurations

This directory contains deployment configurations for every major platform.

```
deploy/
├── helm/                          # Kubernetes Helm chart (full stack)
│   └── finmind/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── _helpers.tpl
│           ├── secrets.yaml
│           ├── configmap.yaml
│           ├── serviceaccount.yaml
│           ├── backend-deployment.yaml
│           ├── backend-service.yaml
│           ├── backend-hpa.yaml
│           ├── frontend-deployment.yaml
│           ├── frontend-service.yaml
│           ├── frontend-hpa.yaml
│           ├── postgres-deployment.yaml
│           ├── postgres-service.yaml
│           ├── postgres-pvc.yaml
│           ├── redis-deployment.yaml
│           ├── redis-service.yaml
│           ├── ingress.yaml
│           ├── servicemonitor.yaml
│           └── NOTES.txt
├── k8s/                           # Raw Kubernetes manifests (existing)
│   ├── namespace.yaml
│   ├── app-stack.yaml
│   ├── monitoring-stack.yaml
│   └── secrets.example.yaml
├── paas/                          # Platform-as-a-Service configs
│   ├── railway/                   # Railway
│   │   ├── railway.toml
│   │   └── README.md
│   ├── heroku/                    # Heroku
│   │   ├── heroku.yml
│   │   ├── app.json
│   │   └── README.md
│   ├── digitalocean/              # DigitalOcean App Platform
│   │   ├── do-app.yaml
│   │   └── README.md
│   ├── render/                    # Render
│   │   ├── render.yaml
│   │   └── README.md
│   ├── flyio/                     # Fly.io
│   │   ├── fly.toml
│   │   └── README.md
│   ├── netlify/                   # Netlify (frontend only)
│   │   ├── netlify.toml
│   │   └── README.md
│   └── vercel/                    # Vercel (frontend only)
│       ├── vercel.json
│       └── README.md
└── cloud/                         # Cloud provider configs
    ├── aws-ecs/                   # AWS ECS Fargate
    │   ├── cloudformation.json
    │   └── README.md
    ├── gcp-cloudrun/              # GCP Cloud Run
    │   ├── deploy-cloudrun.sh
    │   └── README.md
    └── azure-container-apps/      # Azure Container Apps
        ├── deploy-azure.sh
        └── README.md
```

## Quick Reference

| Platform | Type | Config File | Free Tier |
|----------|------|-------------|-----------|
| **Docker Compose** | Local | `docker-compose.yml` | ✅ |
| **Kubernetes (Helm)** | K8s | `deploy/helm/finmind/` | — |
| **Kubernetes (raw)** | K8s | `deploy/k8s/` | — |
| **Tilt** | Local K8s | `Tiltfile` | ✅ |
| **Railway** | PaaS | `deploy/paas/railway/` | ✅ |
| **Heroku** | PaaS | `deploy/paas/heroku/` | ✅ |
| **DigitalOcean** | PaaS | `deploy/paas/digitalocean/` | — |
| **Render** | PaaS | `deploy/paas/render/` | ✅ |
| **Fly.io** | PaaS | `deploy/paas/flyio/` | ✅ |
| **Netlify** | Static | `deploy/paas/netlify/` | ✅ |
| **Vercel** | Static | `deploy/paas/vercel/` | ✅ |
| **AWS ECS Fargate** | Cloud | `deploy/cloud/aws-ecs/` | — |
| **GCP Cloud Run** | Cloud | `deploy/cloud/gcp-cloudrun/` | ✅ |
| **Azure Container Apps** | Cloud | `deploy/cloud/azure-container-apps/` | — |

See each subdirectory's `README.md` for platform-specific instructions.
