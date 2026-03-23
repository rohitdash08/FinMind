# -*- mode: python -*-
# FinMind Tiltfile — local Kubernetes development workflow
# Prerequisites: Tilt (https://tilt.dev), a local K8s cluster (kind/minikube/Docker Desktop)

# ─── Configuration ───────────────────────────────────────────────────────────

# Allow deploying to the current kubectl context (restrict as needed)
allow_k8s_contexts(k8s_context())

# Load .env for local overrides
load('ext://dotenv', 'dotenv')
dotenv()

# ─── Container Images ────────────────────────────────────────────────────────

# Backend — live-reload via Tilt's live_update
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        run('pip install -r requirements.txt', trigger='./packages/backend/requirements.txt'),
    ],
)

# Frontend — live-reload
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        sync('./app/index.html', '/app/index.html'),
        run('npm install', trigger='./app/package.json'),
    ],
)

# ─── Kubernetes Resources ────────────────────────────────────────────────────

# Apply namespace first
k8s_yaml('deploy/k8s/namespace.yaml')

# Create dev secrets (uses defaults from .env.example if .env is absent)
local_resource(
    'create-secrets',
    cmd='''
    kubectl create namespace finmind --dry-run=client -o yaml | kubectl apply -f - && \
    kubectl create secret generic finmind-secrets \
      --namespace=finmind \
      --from-literal=POSTGRES_USER="${POSTGRES_USER:-finmind}" \
      --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-finmind}" \
      --from-literal=POSTGRES_DB="${POSTGRES_DB:-finmind}" \
      --from-literal=JWT_SECRET="${JWT_SECRET:-dev-secret-change}" \
      --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
      --dry-run=client -o yaml | kubectl apply -f -
    ''',
    deps=['.env'],
)

# Deploy the full application stack
k8s_yaml('deploy/k8s/app-stack.yaml')

# ─── Resource Configuration ──────────────────────────────────────────────────

# Backend
k8s_resource(
    'backend',
    port_forwards=['8000:8000'],
    resource_deps=['create-secrets', 'postgres', 'redis'],
    labels=['app'],
)

# Frontend (using dev server via docker-compose, or the nginx build for k8s)
# For local dev, we port-forward the frontend service
k8s_resource(
    'nginx',
    port_forwards=['8080:80'],
    resource_deps=['backend'],
    labels=['app'],
    new_name='frontend-proxy',
)

# Data stores
k8s_resource(
    'postgres',
    port_forwards=['5432:5432'],
    resource_deps=['create-secrets'],
    labels=['data'],
)

k8s_resource(
    'redis',
    port_forwards=['6379:6379'],
    labels=['data'],
)

# ─── Monitoring (optional — uncomment to deploy) ─────────────────────────────

# k8s_yaml('deploy/k8s/monitoring-stack.yaml')
# k8s_resource('prometheus', port_forwards=['9090:9090'], labels=['monitoring'])
# k8s_resource('grafana', port_forwards=['3000:3000'], labels=['monitoring'])

# ─── Custom Buttons ──────────────────────────────────────────────────────────

# Run backend tests
local_resource(
    'backend-tests',
    cmd='docker compose exec backend pytest tests/ -v',
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['test'],
)

# Init database manually
local_resource(
    'init-db',
    cmd='kubectl exec -n finmind deploy/backend -- python -m flask --app wsgi:app init-db',
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['ops'],
)
