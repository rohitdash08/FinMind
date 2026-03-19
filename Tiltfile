# FinMind Tiltfile - Local Kubernetes Development Workflow
# Usage: tilt up
# Prerequisites: Docker, kubectl, a local K8s cluster (minikube/kind/k3d)

# ============================================================
# Configuration
# ============================================================
load('ext://namespace', 'namespace_create')
load('ext://helm_resource', 'helm_resource')

# Allow connections from any host (for remote dev)
allow_k8s_contexts(k8s_context())

# Create namespace
namespace_create('finmind')

# ============================================================
# Docker Builds with Live Reload
# ============================================================

# Backend: build image with live-reload via gunicorn --reload
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        run('pip install -r requirements.txt', trigger=['./packages/backend/requirements.txt']),
    ],
)

# Frontend: build image with Vite dev server hot-reload
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        sync('./app/index.html', '/app/index.html'),
        run('npm install', trigger=['./app/package.json']),
    ],
)

# ============================================================
# Kubernetes Resources (ordered by dependency)
# ============================================================

# Secrets (must be applied before anything else)
k8s_yaml('deploy/k8s/secrets.example.yaml')

# Database layer
k8s_yaml('deploy/k8s/namespace.yaml')

# Apply the full app stack
k8s_yaml('deploy/k8s/app-stack.yaml')

# ============================================================
# Resource Dependencies (enforce startup order)
# ============================================================

# Group resources for the Tilt UI
k8s_resource('postgres',
    labels=['data'],
    port_forwards=['5432:5432'],
)

k8s_resource('redis',
    labels=['data'],
    port_forwards=['6379:6379'],
    resource_deps=['postgres'],
)

k8s_resource('backend',
    labels=['app'],
    port_forwards=['8000:8000'],
    resource_deps=['postgres', 'redis'],
)

k8s_resource('nginx',
    labels=['app'],
    port_forwards=['8080:80'],
    resource_deps=['backend'],
)

# Monitoring stack (optional - lower priority)
k8s_yaml('deploy/k8s/monitoring-stack.yaml')

k8s_resource('postgres-exporter',
    labels=['monitoring'],
    resource_deps=['postgres'],
)

k8s_resource('redis-exporter',
    labels=['monitoring'],
    resource_deps=['redis'],
)

k8s_resource('nginx-exporter',
    labels=['monitoring'],
    resource_deps=['nginx'],
)

# ============================================================
# Local Development Buttons
# ============================================================

# Button to run backend tests
local_resource(
    'backend-tests',
    cmd='cd packages/backend && python -m pytest tests/ -v',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

# Button to run frontend tests
local_resource(
    'frontend-tests',
    cmd='cd app && npm test -- --watchAll=false',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

# Button to initialize/reset database
local_resource(
    'init-db',
    cmd='kubectl exec -n finmind deploy/backend -- python -m flask --app wsgi:app init-db',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    resource_deps=['backend'],
)

print("""
===========================================
  FinMind Local Development Environment
===========================================
  Frontend:  http://localhost:5173
  Backend:   http://localhost:8000
  Nginx:     http://localhost:8080
  Postgres:  localhost:5432
  Redis:     localhost:6379
===========================================
  Run 'tilt up' to start all services
  Press (s) for a snapshot of all resources
===========================================
""")
