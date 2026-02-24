# -*- mode: Python -*-
# Tiltfile for FinMind local K8s development

# Build backend image with live reload
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

# Build frontend image with live reload
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        run('npm install', trigger=['./app/package.json']),
    ],
)

# Deploy using Helm chart
k8s_yaml(helm(
    './deploy/helm/finmind',
    name='finmind-dev',
    values=['./deploy/helm/finmind/values.yaml'],
    set=[
        'backend.image.repository=finmind-backend',
        'backend.image.tag=latest',
        'frontend.image.repository=finmind-frontend',
        'frontend.image.tag=latest',
        'backend.autoscaling.enabled=false',
        'frontend.autoscaling.enabled=false',
        'backend.replicaCount=1',
        'frontend.replicaCount=1',
        'ingress.enabled=false',
    ],
))

# Port forwards for local access
k8s_resource('finmind-dev-backend', port_forwards='8000:8000')
k8s_resource('finmind-dev-frontend', port_forwards='3000:80')
k8s_resource('finmind-dev-postgres', port_forwards='5432:5432')
k8s_resource('finmind-dev-redis', port_forwards='6379:6379')
