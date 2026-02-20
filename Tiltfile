# Tiltfile for FinMind local Kubernetes development
# Prerequisites:
#   - Docker Desktop with Kubernetes enabled OR minikube/kind
#   - Tilt installed: https://docs.tilt.dev/install.html
#   - kubectl configured with local cluster context
#   - Helm 3 installed

# Allow access from host machine
allow_k8s_contexts('docker-desktop')
allow_k8s_contexts('minikube')
allow_k8s_contexts('kind-*')

# Load environment variables from .env
load('ext://dotenv', 'dotenv')
dotenv(fn='.env')

# Build Docker images
docker_build(
    'finmind/backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        run('pip install -r /app/requirements.txt', trigger='./packages/backend/requirements.txt'),
    ],
)

docker_build(
    'finmind/frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        run('cd /app && npm install', trigger='./app/package.json'),
    ],
)

# Install Helm chart
k8s_yaml(
    helm(
        './deploy/kubernetes/helm/finmind',
        name='finmind',
        namespace='finmind',
        values=['./deploy/kubernetes/helm/finmind/values.yaml'],
        set=[
            'backend.image.repository=finmind/backend',
            'backend.image.tag=latest',
            'frontend.image.repository=finmind/frontend',
            'frontend.image.tag=latest',
            'ingress.enabled=false',  # Use port-forward for local dev
            'backend.autoscaling.enabled=false',  # Disable HPA for local dev
            'frontend.autoscaling.enabled=false',
            'postgresql.persistence.enabled=false',  # Use emptyDir for local dev
        ]
    )
)

# Resource dependencies
k8s_resource(
    'finmind-postgresql',
    port_forwards='5432:5432',
    labels=['database'],
)

k8s_resource(
    'finmind-redis',
    port_forwards='6379:6379',
    labels=['cache'],
)

k8s_resource(
    'finmind-backend',
    port_forwards='8000:8000',
    resource_deps=['finmind-postgresql', 'finmind-redis'],
    labels=['backend'],
)

k8s_resource(
    'finmind-frontend',
    port_forwards='3000:80',
    resource_deps=['finmind-backend'],
    labels=['frontend'],
)

# Local URLs
print("""
╔════════════════════════════════════════════════════════════╗
║              FinMind Local Development                     ║
╠════════════════════════════════════════════════════════════╣
║  Frontend:    http://localhost:3000                        ║
║  Backend:     http://localhost:8000                        ║
║  PostgreSQL:  localhost:5432                               ║
║  Redis:       localhost:6379                               ║
║                                                            ║
║  Press 'space' to open Tilt UI                            ║
╚════════════════════════════════════════════════════════════╝
""")
