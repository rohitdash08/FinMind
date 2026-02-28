# Tilt Local Kubernetes Development

Tilt provides a seamless local Kubernetes development experience with live-reload, log aggregation, and one-command setup.

## Prerequisites

1. **Docker Desktop** or **Rancher Desktop** with Kubernetes enabled
2. **Tilt** - Install from [https://docs.tilt.dev/install.html](https://docs.tilt.dev/install.html)
3. **kubectl** - Kubernetes CLI

### Quick Install (macOS)
```bash
brew install tilt-dev/tap/tilt
```

### Quick Install (Linux)
```bash
curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | bash
```

### Quick Install (Windows)
```powershell
iex ((new-object net.webclient).DownloadString('https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.ps1'))
```

## Setup

1. **Enable Kubernetes** in Docker Desktop/Rancher Desktop
   - Docker Desktop: Settings → Kubernetes → Enable Kubernetes
   - Rancher Desktop: Already enabled by default

2. **Create secrets file**:
   ```bash
   cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
   ```

3. **Edit secrets** with your values:
   ```yaml
   # deploy/k8s/secrets.yaml
   data:
     JWT_SECRET: <base64-encoded-secret>
     POSTGRES_USER: ZmlubWluZA==  # finmind
     POSTGRES_PASSWORD: <base64-encoded-password>
     POSTGRES_DB: ZmlubWluZA==    # finmind
     GEMINI_API_KEY: <base64-encoded-api-key>
   ```
   
   Generate base64:
   ```bash
   echo -n "your-secret" | base64
   ```

## Running

From the project root:

```bash
tilt up
```

This will:
- Build Docker images for backend and frontend
- Deploy all Kubernetes resources
- Set up port forwards
- Watch for code changes and live-reload

## Access

| Service | URL |
|---------|-----|
| **Backend API** | http://localhost:8000 |
| **Nginx Proxy** | http://localhost:8080 |
| **PostgreSQL** | localhost:5432 |
| **Redis** | localhost:6379 |
| **Tilt Dashboard** | http://localhost:10350 |

With monitoring enabled:
| Service | URL |
|---------|-----|
| **Grafana** | http://localhost:3000 |
| **Prometheus** | http://localhost:9090 |

## Development Workflow

### Live Reload

Tilt automatically syncs changes:
- **Backend**: Changes to `packages/backend/app/` are synced live
- **Frontend**: Changes to `app/src/` are synced live

No rebuild needed for most changes!

### Manual Actions

In the Tilt dashboard (http://localhost:10350):
- Click **Trigger Update** on any resource to force rebuild
- Run **backend-tests** or **frontend-tests** manually
- View logs for all services in one place

### Running Tests

From Tilt dashboard, trigger:
- `backend-tests` - Run pytest
- `frontend-tests` - Run npm test

Or via command line:
```bash
# Backend tests
docker compose exec backend pytest tests/ -v

# Frontend tests
docker compose exec frontend-dev npm test
```

## Configuration

### Enable Production Mode

```bash
tilt up -- --production
```

This enables the monitoring stack (Prometheus, Grafana).

### Custom Image Registry

Edit the `Tiltfile` to push images to your registry:
```python
docker_build(
    'your-registry/finmind-backend',
    context='./packages/backend',
    ...
)
```

### Resource Dependencies

The Tiltfile defines dependencies:
```
postgres → backend → nginx
redis   ↗
```

Tilt ensures services start in the correct order.

## Troubleshooting

### Kubernetes Not Running
```bash
# Check kubectl context
kubectl config current-context

# Should show: docker-desktop or rancher-desktop
```

### Image Build Fails
```bash
# Check Docker is running
docker info

# Manually build to see errors
docker build -t finmind-backend ./packages/backend
```

### Pods Not Starting
```bash
# Check pod status
kubectl get pods -n finmind

# View pod logs
kubectl logs -n finmind deployment/backend

# Describe pod for events
kubectl describe pod -n finmind -l app=backend
```

### Port Already in Use
```bash
# Find process using port
lsof -i :8000

# Kill it or change port in Tiltfile
kill -9 <PID>
```

## Cleanup

Stop Tilt with `Ctrl+C`, then:

```bash
# Remove all Kubernetes resources
kubectl delete namespace finmind

# Or just the app resources
kubectl delete -f deploy/k8s/app-stack.yaml
```

## Comparison: Tilt vs Docker Compose

| Feature | Tilt | Docker Compose |
|---------|------|----------------|
| **Environment** | Kubernetes (local/remote) | Docker only |
| **Live Reload** | Yes, with sync | Needs volume mounts |
| **Production Parity** | High (same K8s manifests) | Medium |
| **Dashboard** | Rich web UI | CLI only |
| **Multi-service Logs** | Aggregated | Separate |
| **Learning Curve** | Medium | Low |

**Use Tilt when:**
- You deploy to Kubernetes in production
- You want to test Kubernetes features locally
- Your team needs a unified K8s workflow

**Use Docker Compose when:**
- You want the simplest setup
- You don't use Kubernetes in production
- You need quick local iteration

## Resources

- [Tilt Documentation](https://docs.tilt.dev/)
- [Tiltfile API Reference](https://docs.tilt.dev/api.html)
- [Example Tiltfiles](https://github.com/tilt-dev/tilt-example-html)
