# ============================================================================
# FinMind — Tilt local Kubernetes development workflow
# ============================================================================
#
# Prerequisites:
#   - Docker Desktop or Rancher Desktop with Kubernetes enabled
#   - Tilt installed: https://docs.tilt.dev/install.html
#   - kubectl configured for local cluster
#
# Usage:
#   tilt up              # Start development
#   tilt down            # Tear down
#   tilt ci              # CI mode (no UI, exit on failure)
#
# Dashboard: http://localhost:10350
# Frontend:  http://localhost:5173  (via port-forward)
# Backend:   http://localhost:8000  (via port-forward)
# ============================================================================

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

allow_k8s_contexts(['docker-desktop', 'rancher-desktop', 'minikube', 'kind-kind', 'colima'])

load('ext://namespace', 'namespace_create', 'namespace_inject')
namespace_create('finmind')

# ---------------------------------------------------------------------------
# Docker builds with live-reload
# ---------------------------------------------------------------------------

# Backend — Python/Flask with hot-reload via volume sync
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

# Frontend — React/Vite with hot-reload
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    target='builder',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        run('npm install', trigger=['./app/package.json']),
    ],
)

# ---------------------------------------------------------------------------
# Kubernetes resources (from kustomize-style raw manifests)
# ---------------------------------------------------------------------------

# Infrastructure — postgres, redis, secrets, config
k8s_yaml([
    'deploy/tilt/namespace.yaml',
    'deploy/tilt/secrets.yaml',
    'deploy/tilt/configmap.yaml',
    'deploy/tilt/postgres.yaml',
    'deploy/tilt/redis.yaml',
    'deploy/tilt/backend.yaml',
    'deploy/tilt/frontend.yaml',
])

# ---------------------------------------------------------------------------
# Resource grouping and port-forwards
# ---------------------------------------------------------------------------

k8s_resource('postgres',
    labels=['infra'],
    port_forwards=['5432:5432'],
)

k8s_resource('redis',
    labels=['infra'],
    port_forwards=['6379:6379'],
)

k8s_resource('backend',
    labels=['app'],
    port_forwards=['8000:8000'],
    resource_deps=['postgres', 'redis'],
)

k8s_resource('frontend',
    labels=['app'],
    port_forwards=['5173:80'],
    resource_deps=['backend'],
)

# ---------------------------------------------------------------------------
# Local commands for convenience
# ---------------------------------------------------------------------------

local_resource(
    'db-seed',
    cmd='kubectl exec -n finmind deploy/backend -- python -m flask --app wsgi:app init-db',
    labels=['tasks'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

local_resource(
    'run-tests',
    cmd='cd packages/backend && python -m pytest tests/ -v --tb=short',
    labels=['tasks'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)
