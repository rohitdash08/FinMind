# -*- mode: Python -*-
# Tiltfile for FinMind local development

# Load extensions
load('ext://restart_process', 'docker_build_with_restart')
load('ext://helm_resource', 'helm_resource', 'helm_repo')

# Settings
allow_k8s_contexts(['docker-desktop', 'minikube', 'kind-finmind'])

# Build backend image
docker_build(
    'finmind-backend',
    context='.',
    dockerfile='app/backend/Dockerfile',
    live_update=[
        sync('./app/backend', '/app'),
        run('pip install -r /app/requirements.txt', trigger=['./app/backend/requirements.txt']),
    ]
)

# Build frontend image
docker_build(
    'finmind-frontend',
    context='.',
    dockerfile='app/frontend/Dockerfile',
    live_update=[
        sync('./app/frontend/src', '/app/src'),
        run('npm install', trigger=['./app/frontend/package.json']),
    ]
)

# Deploy with Helm
helm_resource(
    'finmind',
    chart='./deploy/helm',
    namespace='finmind',
    flags=[
        '--create-namespace',
        '--values=./deploy/helm/values.yaml',
        '--set=image.backend.tag=latest',
        '--set=image.frontend.tag=latest',
    ],
    resource_deps=['finmind-backend', 'finmind-frontend'],
    port_forwards=[
        '8000:8000',  # Backend API
        '3000:3000',  # Frontend
    ]
)

# Health check
local_resource(
    'health-check',
    cmd='curl -sf http://localhost:8000/api/health/ && echo "Backend OK"',
    resource_deps=['finmind'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)
