# FinMind Tiltfile — local Kubernetes development

# Build backend image (matches K8s manifest image reference)
docker_build('ghcr.io/rohitdash08/finmind-backend', './packages/backend',
  live_update=[
    sync('./packages/backend/app', '/app/app'),
    sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
    run('pip install -r requirements.txt', trigger=['./packages/backend/requirements.txt']),
  ]
)

# Build frontend image for local development.
# The K8s manifests use a separate nginx reverse proxy; this image can be
# deployed manually or used when a frontend K8s Deployment is added.
docker_build('ghcr.io/rohitdash08/finmind-frontend', './app')

# Apply K8s manifests
k8s_yaml([
  'deploy/k8s/namespace.yaml',
  'deploy/k8s/secrets.example.yaml',
  'deploy/k8s/app-stack.yaml',
])

# Resource grouping and dependencies
k8s_resource('postgres', labels=['database'],
  port_forwards='5432:5432')

k8s_resource('redis', labels=['database'],
  port_forwards='6379:6379')

k8s_resource('backend', labels=['app'],
  port_forwards='8000:8000',
  resource_deps=['postgres', 'redis'])

k8s_resource('nginx', labels=['app'],
  port_forwards='8080:80',
  resource_deps=['backend'])
