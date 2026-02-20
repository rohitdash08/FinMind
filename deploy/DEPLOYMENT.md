# FinMind Deployment Guide

Complete deployment guide for FinMind across all major cloud platforms.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Compose (Local Development)](#docker-compose-local-development)
- [Kubernetes (Production)](#kubernetes-production)
- [Tilt (Local Kubernetes Development)](#tilt-local-kubernetes-development)
- [Cloud Platform Deployments](#cloud-platform-deployments)
  - [Railway](#railway)
  - [Heroku](#heroku)
  - [Render](#render)
  - [Fly.io](#flyio)
  - [DigitalOcean](#digitalocean)
  - [AWS ECS Fargate](#aws-ecs-fargate)
  - [GCP Cloud Run](#gcp-cloud-run)
  - [Azure Container Apps](#azure-container-apps)
  - [Vercel (Frontend)](#vercel-frontend)
  - [Netlify (Frontend)](#netlify-frontend)

---

## Prerequisites

### General Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Git
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Kubernetes Requirements
- kubectl 1.25+
- Helm 3.0+
- A Kubernetes cluster (local: Docker Desktop/minikube/kind, cloud: GKE/EKS/AKS)

### Tilt Requirements
- Tilt 0.30+ ([installation guide](https://docs.tilt.dev/install.html))
- Local Kubernetes cluster

---

## Docker Compose (Local Development)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
nano .env

# Start all services
docker-compose up --build

# Access the application
# Frontend: http://localhost:5173
# Backend: http://localhost:8000
```

### Environment Configuration

Edit `.env` file with your settings:

```bash
# Database
DATABASE_URL="postgresql+psycopg2://finmind:finmind@postgres:5432/finmind"
POSTGRES_USER="finmind"
POSTGRES_PASSWORD="finmind"
POSTGRES_DB="finmind"

# Redis
REDIS_URL="redis://redis:6379/0"

# JWT
JWT_SECRET="your-secret-key-here"

# AI Services (optional)
OPENAI_API_KEY=""
GEMINI_API_KEY=""
GEMINI_MODEL="gemini-1.5-flash"

# Notifications (optional)
TWILIO_ACCOUNT_SID=""
TWILIO_AUTH_TOKEN=""
TWILIO_WHATSAPP_FROM=""
EMAIL_FROM=""
SMTP_URL=""

# Frontend
VITE_API_URL="http://localhost:8000"
```

---

## Kubernetes (Production)

### Using Helm Chart

Our production-ready Helm chart includes:
- ✅ PostgreSQL StatefulSet with persistent storage
- ✅ Redis deployment
- ✅ Backend deployment with health probes
- ✅ Frontend deployment
- ✅ Horizontal Pod Autoscaling (HPA)
- ✅ Ingress with TLS support
- ✅ ConfigMaps and Secrets management
- ✅ ServiceMonitor for Prometheus
- ✅ PodDisruptionBudget

### Installation Steps

```bash
# 1. Create namespace
kubectl create namespace finmind

# 2. Create secrets (replace with your actual values)
kubectl create secret generic finmind-secrets \
  --from-literal=JWT_SECRET='your-jwt-secret' \
  --from-literal=POSTGRES_PASSWORD='your-postgres-password' \
  --from-literal=OPENAI_API_KEY='your-openai-key' \
  -n finmind

# 3. Install Helm chart
helm install finmind ./deploy/kubernetes/helm/finmind \
  --namespace finmind \
  --set backend.secrets.JWT_SECRET='your-jwt-secret' \
  --set postgresql.auth.password='your-postgres-password' \
  --set ingress.hosts[0].host='your-domain.com'

# 4. Verify deployment
kubectl get pods -n finmind
kubectl get svc -n finmind

# 5. Access the application
kubectl port-forward svc/finmind-frontend 3000:80 -n finmind
kubectl port-forward svc/finmind-backend 8000:8000 -n finmind
```

### Custom Values

Create a `custom-values.yaml`:

```yaml
backend:
  replicaCount: 3
  resources:
    requests:
      memory: "512Mi"
      cpu: "500m"
    limits:
      memory: "1Gi"
      cpu: "1000m"

ingress:
  enabled: true
  hosts:
    - host: finmind.yourdomain.com
      paths:
        - path: /api
          pathType: Prefix
          backend: backend
        - path: /
          pathType: Prefix
          backend: frontend
  tls:
    - secretName: finmind-tls
      hosts:
        - finmind.yourdomain.com

postgresql:
  persistence:
    size: 20Gi
```

Install with custom values:

```bash
helm install finmind ./deploy/kubernetes/helm/finmind \
  -f custom-values.yaml \
  --namespace finmind
```

### Upgrading

```bash
helm upgrade finmind ./deploy/kubernetes/helm/finmind \
  -f custom-values.yaml \
  --namespace finmind
```

### Uninstalling

```bash
helm uninstall finmind --namespace finmind
kubectl delete namespace finmind
```

---

## Tilt (Local Kubernetes Development)

Tilt provides a modern dev experience for Kubernetes with live updates.

### Setup

```bash
# 1. Ensure you have a local Kubernetes cluster running
# Docker Desktop: Enable Kubernetes in settings
# OR
minikube start
# OR
kind create cluster

# 2. Install Tilt
# macOS
brew install tilt-dev/tap/tilt

# Linux
curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | bash

# 3. Start Tilt
tilt up

# 4. Access Tilt UI (opens automatically)
# http://localhost:10350
```

### Features

- 🔄 **Live Reload**: Changes to code automatically rebuild and deploy
- 📊 **Resource Visualization**: See all services, logs, and metrics in one place
- 🐛 **Easy Debugging**: Click on any service to see logs
- ⚡ **Fast Iteration**: Incremental builds for rapid development

### Tilt Commands

```bash
# Start Tilt
tilt up

# Start Tilt with specific resources
tilt up backend frontend

# View logs
tilt logs backend

# Trigger manual update
tilt trigger backend

# Stop Tilt (keeps resources running)
tilt down

# Stop Tilt and delete resources
tilt down --delete-namespaces
```

---

## Cloud Platform Deployments

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize project
railway init

# 4. Add PostgreSQL
railway add --plugin postgresql

# 5. Add Redis
railway add --plugin redis

# 6. Set environment variables
railway variables set JWT_SECRET=your-secret-here

# 7. Deploy
railway up
```

Configuration: `deploy/platforms/railway.json`

---

### Heroku

```bash
# 1. Install Heroku CLI
brew tap heroku/brew && brew install heroku

# 2. Login
heroku login

# 3. Create app
heroku create finmind-app

# 4. Add addons
heroku addons:create heroku-postgresql:mini
heroku addons:create heroku-redis:mini

# 5. Set config vars
heroku config:set JWT_SECRET=your-secret-here

# 6. Deploy
git push heroku main
```

Configuration: `deploy/platforms/heroku.json`

---

### Render

```bash
# 1. Create account at render.com

# 2. Create new Blueprint
# Upload render.yaml from deploy/platforms/render.yaml

# 3. Configure environment variables in dashboard

# 4. Deploy automatically on git push
```

Configuration: `deploy/platforms/render.yaml`

---

### Fly.io

```bash
# 1. Install flyctl
brew install flyctl

# 2. Login
fly auth login

# 3. Launch app (backend)
fly launch --config deploy/platforms/fly.toml

# 4. Create Postgres
fly postgres create --name finmind-db

# 5. Attach database
fly postgres attach finmind-db

# 6. Create Redis
fly redis create --name finmind-redis

# 7. Set secrets
fly secrets set JWT_SECRET=your-secret-here

# 8. Deploy
fly deploy
```

Configuration: `deploy/platforms/fly.toml`

---

### DigitalOcean

#### App Platform

```bash
# 1. Install doctl
brew install doctl

# 2. Authenticate
doctl auth init

# 3. Create app
doctl apps create --spec deploy/platforms/digitalocean-app.yaml

# 4. Configure environment variables in dashboard
# https://cloud.digitalocean.com/apps
```

#### Droplet (Docker)

```bash
# 1. Create droplet
doctl compute droplet create finmind \
  --image docker-20-04 \
  --size s-1vcpu-1gb \
  --region nyc1

# 2. SSH into droplet
doctl compute ssh finmind

# 3. Clone repo and deploy
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind
cp .env.example .env
nano .env  # Configure environment
docker-compose up -d
```

Configuration: `deploy/platforms/digitalocean-app.yaml`

---

### AWS ECS Fargate

```bash
# 1. Install AWS CLI
brew install awscli

# 2. Configure AWS credentials
aws configure

# 3. Create ECR repositories
aws ecr create-repository --repository-name finmind-backend
aws ecr create-repository --repository-name finmind-frontend

# 4. Build and push images
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker build -t finmind-backend ./packages/backend
docker tag finmind-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

# 5. Create ECS cluster
aws ecs create-cluster --cluster-name finmind

# 6. Register task definition
aws ecs register-task-definition --cli-input-json file://deploy/platforms/aws-ecs-task-definition.json

# 7. Create service
aws ecs create-service \
  --cluster finmind \
  --service-name finmind-backend \
  --task-definition finmind-backend \
  --desired-count 2 \
  --launch-type FARGATE
```

Configuration: `deploy/platforms/aws-ecs-task-definition.json`

---

### GCP Cloud Run

```bash
# 1. Install gcloud CLI
brew install google-cloud-sdk

# 2. Authenticate
gcloud auth login
gcloud config set project PROJECT_ID

# 3. Build image
gcloud builds submit --tag gcr.io/PROJECT_ID/finmind-backend ./packages/backend

# 4. Deploy
gcloud run deploy finmind-backend \
  --image gcr.io/PROJECT_ID/finmind-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars LOG_LEVEL=INFO \
  --set-secrets DATABASE_URL=finmind-database-url:latest \
  --min-instances 1 \
  --max-instances 10
```

Configuration: `deploy/platforms/gcp-cloudrun.yaml`

---

### Azure Container Apps

```bash
# 1. Install Azure CLI
brew install azure-cli

# 2. Login
az login

# 3. Create resource group
az group create --name finmind-rg --location eastus

# 4. Create container registry
az acr create --resource-group finmind-rg --name finmindacr --sku Basic

# 5. Build and push image
az acr build --registry finmindacr --image backend:latest ./packages/backend

# 6. Create Container Apps environment
az containerapp env create \
  --name finmind-env \
  --resource-group finmind-rg \
  --location eastus

# 7. Deploy
az containerapp create \
  --name finmind-backend \
  --resource-group finmind-rg \
  --environment finmind-env \
  --image finmindacr.azurecr.io/backend:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10
```

Configuration: `deploy/platforms/azure-container-app.yaml`

---

### Vercel (Frontend)

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. Login
vercel login

# 3. Deploy
cd app
vercel --prod

# 4. Set environment variables
vercel env add VITE_API_URL production
```

---

### Netlify (Frontend)

```bash
# 1. Install Netlify CLI
npm install -g netlify-cli

# 2. Login
netlify login

# 3. Build frontend
cd app
npm run build

# 4. Deploy
netlify deploy --prod --dir=dist
```

---

## Health Checks & Monitoring

All deployments include health check endpoints:

- **Liveness**: `GET /health` - Returns 200 if application is running
- **Readiness**: `GET /ready` - Returns 200 if application can handle requests (DB connected)

### Prometheus Metrics

When monitoring is enabled (Kubernetes), metrics are exposed at:
- Backend: `http://backend:8000/metrics`

---

## Troubleshooting

### Database Connection Issues

```bash
# Check database pod
kubectl logs -n finmind finmind-postgresql-0

# Test connection
kubectl exec -n finmind finmind-postgresql-0 -- psql -U finmind -d finmind -c "SELECT 1"
```

### Pod Crashes

```bash
# Check pod logs
kubectl logs -n finmind <pod-name>

# Describe pod
kubectl describe pod -n finmind <pod-name>

# Check events
kubectl get events -n finmind --sort-by='.lastTimestamp'
```

### Ingress Not Working

```bash
# Check ingress
kubectl get ingress -n finmind
kubectl describe ingress -n finmind finmind

# Check ingress controller
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller
```

---

## Security Best Practices

1. **Never commit secrets** - Use environment variables or secret managers
2. **Use TLS/HTTPS** - Enable cert-manager for automatic certificate management
3. **Rotate JWT secrets** - Change JWT_SECRET periodically
4. **Limit database access** - Use network policies to restrict access
5. **Enable security scanning** - Use tools like Trivy, Snyk for container scanning
6. **Use least privilege** - Run containers as non-root users
7. **Keep dependencies updated** - Regularly update base images and packages

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/rohitdash08/FinMind/issues
- Discord: @geekster007 (required for bounty eligibility)

---

## License

MIT License - see LICENSE file for details
