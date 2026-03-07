# FinMind — Tilt local Kubernetes development
# Usage: tilt up

# Build backend image with live-update
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

# Build frontend image with live-update
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

# Apply K8s manifests
k8s_yaml([
    'deploy/k8s/namespace.yaml',
    'deploy/k8s/secrets.example.yaml',
    'deploy/k8s/app-stack.yaml',
])

# Override image references to use local builds
k8s_image_json_path(
    '{.spec.template.spec.containers[0].image}',
)

# Resource grouping for the Tilt UI
k8s_resource('postgres', labels=['data'])
k8s_resource('redis', labels=['data'])
k8s_resource('backend', labels=['app'],
    port_forwards=['8000:8000'],
    resource_deps=['postgres', 'redis'],
)
k8s_resource('nginx', labels=['app'],
    port_forwards=['8080:80'],
    resource_deps=['backend'],
)

# Local frontend dev server (runs outside K8s for faster iteration)
local_resource(
    'frontend-dev',
    serve_cmd='cd app && npm install && npm run dev -- --host 0.0.0.0 --port 5173',
    labels=['app'],
    links=['http://localhost:5173'],
)
