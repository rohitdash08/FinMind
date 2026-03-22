# Tiltfile — FinMind local Kubernetes dev workflow
# Usage: tilt up
# Prerequisites: Docker, kubectl, a local K8s cluster (kind / minikube / Docker Desktop)

load('ext://helm_resource', 'helm_resource', 'helm_repo')
load('ext://restart_process', 'docker_build_with_restart')

# ── Build images ──────────────────────────────────────────────────────────────
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend', '/app'),
        run('pip install -r /app/requirements.txt', trigger='./packages/backend/requirements.txt'),
    ],
)

docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
    ],
)

# ── Apply K8s manifests ───────────────────────────────────────────────────────
k8s_yaml([
    'deploy/k8s/namespace.yaml',
    'deploy/k8s/app-stack.yaml',
    'deploy/k8s/monitoring-stack.yaml',
])

# ── Resource grouping ─────────────────────────────────────────────────────────
k8s_resource('finmind-backend',  port_forwards='8000:8000', labels=['backend'])
k8s_resource('finmind-frontend', port_forwards='3000:80',   labels=['frontend'])
k8s_resource('postgres',         port_forwards='5432:5432', labels=['data'])
k8s_resource('redis',            port_forwards='6379:6379', labels=['data'])

# ── One-time DB migration ─────────────────────────────────────────────────────
local_resource(
    'db-migrate',
    cmd='kubectl exec -n finmind deploy/finmind-backend -- alembic upgrade head',
    deps=['deploy/k8s/app-stack.yaml'],
    labels=['ops'],
)
