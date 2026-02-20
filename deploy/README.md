# FinMind Deployment Infrastructure

This directory contains all deployment configurations and scripts for FinMind across multiple platforms.

## 📁 Directory Structure

```
deploy/
├── kubernetes/
│   └── helm/
│       └── finmind/          # Production-ready Helm chart
│           ├── Chart.yaml
│           ├── values.yaml
│           └── templates/
│               ├── backend-deployment.yaml
│               ├── frontend-deployment.yaml
│               ├── postgresql-statefulset.yaml
│               ├── redis-deployment.yaml
│               ├── ingress.yaml
│               ├── hpa.yaml (autoscaling)
│               └── servicemonitor.yaml (Prometheus)
│
├── platforms/                 # Platform-specific configs
│   ├── railway.json          # Railway deployment
│   ├── heroku.json           # Heroku deployment
│   ├── render.yaml           # Render deployment
│   ├── fly.toml              # Fly.io deployment
│   ├── digitalocean-app.yaml # DigitalOcean App Platform
│   ├── aws-ecs-task-definition.json  # AWS ECS Fargate
│   ├── gcp-cloudrun.yaml     # GCP Cloud Run
│   └── azure-container-app.yaml      # Azure Container Apps
│
├── tilt/                      # (Reserved for Tilt resources)
├── DEPLOYMENT.md             # Complete deployment guide
└── README.md                 # This file
```

## 🚀 Quick Start

### Local Development (Docker Compose)

```bash
# From repository root
cp .env.example .env
docker-compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000

### Local Kubernetes (Tilt)

```bash
# Ensure local K8s cluster is running
tilt up
```

- Tilt UI: http://localhost:10350
- Frontend: http://localhost:3000
- Backend: http://localhost:8000

### Production Kubernetes (Helm)

```bash
helm install finmind ./kubernetes/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set backend.secrets.JWT_SECRET='your-secret' \
  --set ingress.hosts[0].host='your-domain.com'
```

## 📋 Deployment Options

### ☁️ Cloud Platforms

| Platform | Type | Config File | Difficulty |
|----------|------|-------------|------------|
| **Railway** | PaaS | `platforms/railway.json` | ⭐ Easy |
| **Heroku** | PaaS | `platforms/heroku.json` | ⭐ Easy |
| **Render** | PaaS | `platforms/render.yaml` | ⭐ Easy |
| **Fly.io** | PaaS | `platforms/fly.toml` | ⭐⭐ Medium |
| **DigitalOcean** | PaaS/IaaS | `platforms/digitalocean-app.yaml` | ⭐⭐ Medium |
| **AWS ECS** | Container | `platforms/aws-ecs-task-definition.json` | ⭐⭐⭐ Advanced |
| **GCP Cloud Run** | Serverless | `platforms/gcp-cloudrun.yaml` | ⭐⭐ Medium |
| **Azure** | Container | `platforms/azure-container-app.yaml` | ⭐⭐⭐ Advanced |
| **Kubernetes** | Container | `kubernetes/helm/finmind/` | ⭐⭐⭐ Advanced |

### 🎯 Frontend Only

| Platform | Type | Best For |
|----------|------|----------|
| **Vercel** | Jamstack | React/Vue/Next.js apps |
| **Netlify** | Jamstack | Static sites & SPAs |

## 🛠️ Features

### Kubernetes Helm Chart

Our production-ready Helm chart includes:

- ✅ **High Availability**: Multi-replica deployments
- ✅ **Auto-scaling**: HPA based on CPU/memory
- ✅ **Health Checks**: Liveness and readiness probes
- ✅ **Secrets Management**: Secure credential handling
- ✅ **Database**: PostgreSQL StatefulSet with persistence
- ✅ **Caching**: Redis deployment
- ✅ **Ingress**: TLS-ready with cert-manager support
- ✅ **Observability**: Prometheus ServiceMonitor
- ✅ **Security**: Non-root containers, security contexts
- ✅ **Resilience**: PodDisruptionBudget for safe rolling updates

### Tilt Development

- 🔄 **Live Reload**: Code changes instantly reflected
- 📊 **Unified Dashboard**: All services in one view
- 🐛 **Easy Debugging**: Click to view logs
- ⚡ **Fast Builds**: Incremental updates

## 📖 Documentation

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed deployment instructions for each platform.

## 🔐 Security Considerations

1. **Never commit secrets** to version control
2. Use **environment variables** or secret managers
3. Enable **TLS/HTTPS** in production
4. Rotate **JWT secrets** regularly
5. Use **least privilege** for container security contexts
6. Enable **network policies** to restrict traffic
7. Keep **dependencies updated** regularly

## 🧪 Testing Deployments

### Verify Backend Health

```bash
curl http://your-backend-url/health
# Expected: {"status":"ok"}

curl http://your-backend-url/ready
# Expected: {"status":"ready","database":"connected"}
```

### Verify Frontend

```bash
curl http://your-frontend-url
# Expected: HTML page
```

### Kubernetes Deployment Verification

```bash
# Check all pods are running
kubectl get pods -n finmind

# Check services
kubectl get svc -n finmind

# Check ingress
kubectl get ingress -n finmind

# View logs
kubectl logs -n finmind -l app.kubernetes.io/component=backend --tail=50

# Check autoscaling
kubectl get hpa -n finmind
```

## 📊 Monitoring & Observability

### Metrics Endpoints

- **Backend Health**: `/health`
- **Backend Readiness**: `/ready`
- **Prometheus Metrics**: `/metrics` (when enabled)

### Kubernetes Observability

The Helm chart includes ServiceMonitor for Prometheus integration:

```bash
# Install Prometheus Operator first
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack

# Then enable monitoring in values.yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
```

## 🆘 Troubleshooting

### Common Issues

#### 1. Database Connection Failed

```bash
# Check if PostgreSQL is running
kubectl get pods -n finmind | grep postgresql

# Check logs
kubectl logs -n finmind finmind-postgresql-0

# Test connection
kubectl exec -n finmind finmind-postgresql-0 -- psql -U finmind -c "SELECT 1"
```

#### 2. Pod CrashLoopBackOff

```bash
# Check pod details
kubectl describe pod -n finmind <pod-name>

# Check logs
kubectl logs -n finmind <pod-name> --previous

# Check resource limits
kubectl top pods -n finmind
```

#### 3. Ingress Not Working

```bash
# Verify ingress controller is installed
kubectl get pods -n ingress-nginx

# Check ingress
kubectl describe ingress -n finmind finmind

# Check TLS certificate
kubectl get certificate -n finmind
```

## 🤝 Contributing

When adding new deployment configurations:

1. Test thoroughly in a staging environment
2. Update DEPLOYMENT.md with instructions
3. Add platform to the comparison table above
4. Document any platform-specific quirks
5. Include example environment variables

## 📞 Support

- **GitHub Issues**: [rohitdash08/FinMind/issues](https://github.com/rohitdash08/FinMind/issues)
- **Discord**: @geekster007 (required for bounty eligibility)
- **Documentation**: [DEPLOYMENT.md](./DEPLOYMENT.md)

## 📄 License

MIT License - see [LICENSE](../LICENSE) for details

---

**Built with ❤️ for the FinMind community**
