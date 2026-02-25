# FinMind Tiltfile — Local K8s Development Workflow
# ─────────────────────────────────────────────────
# Prerequisites:
#   1. Install Tilt: https://docs.tilt.dev/install.html
#   2. A local K8s cluster (minikube, kind, Docker Desktop, etc.)
#   3. kubectl configured to point at your local cluster
#   4. Create namespace:  kubectl apply -f deploy/k8s/namespace.yaml
#   5. Create secrets:    kubectl apply -f deploy/k8s/secrets.example.yaml
#        (copy secrets.example.yaml → secrets.yaml, fill real values, apply)
#
# Run:
#   tilt up
#
# Dashboard opens at http://localhost:10350

# ── Docker Builds ──────────────────────────────────

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

# ── K8s Manifests ──────────────────────────────────

k8s_yaml([
    'deploy/k8s/namespace.yaml',
    'deploy/k8s/secrets.example.yaml',
    'deploy/k8s/app-stack.yaml',
])

# ── Image Overrides (match K8s manifest image refs) ─

k8s_image_json_path('{.spec.template.spec.containers[0].image}')

# Override the ghcr image in manifests with our local build
k8s_resource('backend', port_forwards=['8000:8000'], labels=['app'])
k8s_resource('postgres', port_forwards=['5432:5432'], labels=['infra'])
k8s_resource('redis', port_forwards=['6379:6379'], labels=['infra'])
k8s_resource('nginx', port_forwards=['8080:80'], labels=['app'])

# ── Resource Grouping ─────────────────────────────

k8s_resource('postgres-exporter', labels=['monitoring'])
k8s_resource('redis-exporter', labels=['monitoring'])
k8s_resource('nginx-exporter', labels=['monitoring'])
