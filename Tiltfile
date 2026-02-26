# =============================================================================
# FinMind Tiltfile - Local Kubernetes Development with Hot Reload
# =============================================================================
# Prerequisites:
#   - Docker Desktop / Rancher Desktop / minikube with K8s enabled
#   - Tilt installed: https://docs.tilt.dev/install.html
#
# Usage:
#   tilt up          # start dev environment
#   tilt down        # tear down
#   tilt ci          # run in CI mode (no interactive UI)
# =============================================================================

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load('ext://namespace', 'namespace_create')

# Create the finmind namespace if it doesn't exist
namespace_create('finmind')
k8s_namespace('finmind')

# ---------------------------------------------------------------------------
# Backend - Flask API with live reload
# ---------------------------------------------------------------------------
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        # Sync source code changes without rebuilding the image
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        # Reinstall deps only when requirements.txt changes
        fall_back_on(['./packages/backend/requirements.txt']),
    ],
)

# ---------------------------------------------------------------------------
# Frontend - React/Vite with live reload
# ---------------------------------------------------------------------------
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        # Sync source changes
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        sync('./app/index.html', '/app/index.html'),
        # Full rebuild on config changes
        fall_back_on([
            './app/package.json',
            './app/vite.config.ts',
            './app/tailwind.config.js',
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Kubernetes Resources
# ---------------------------------------------------------------------------

# Infrastructure: PostgreSQL + Redis (from existing k8s manifests)
k8s_yaml([
    'deploy/helm/finmind/templates/namespace.yaml',
])

# Apply Tilt-specific K8s manifests
k8s_yaml(helm(
    'deploy/helm/finmind',
    name='finmind-dev',
    namespace='finmind',
    values=['deploy/tilt/values-dev.yaml'],
))

# ---------------------------------------------------------------------------
# Resource Grouping & Port Forwards
# ---------------------------------------------------------------------------
k8s_resource('backend',
    port_forwards=['8000:8000'],
    labels=['app'],
    resource_deps=['postgres', 'redis'],
)

k8s_resource('frontend',
    port_forwards=['5173:80'],
    labels=['app'],
)

k8s_resource('postgres',
    port_forwards=['5432:5432'],
    labels=['infra'],
)

k8s_resource('redis',
    port_forwards=['6379:6379'],
    labels=['infra'],
)

# ---------------------------------------------------------------------------
# Local Resource: run frontend dev server natively (optional, faster HMR)
# ---------------------------------------------------------------------------
# Uncomment below to run frontend outside K8s for faster hot-module-reload:
#
# local_resource(
#     'frontend-local',
#     serve_cmd='cd app && npm install && npm run dev -- --host 0.0.0.0 --port 5173',
#     deps=['app/src', 'app/package.json'],
#     labels=['app'],
# )
