# FinMind Tiltfile — local Kubernetes development

# Build images
docker_build('finmind-backend', './packages/backend',
  live_update=[
    sync('./packages/backend/app', '/app/app'),
    sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
    run('pip install -r requirements.txt', trigger=['./packages/backend/requirements.txt']),
  ]
)

docker_build('finmind-frontend', './app',
  live_update=[
    sync('./app/src', '/app/src'),
    sync('./app/public', '/app/public'),
    run('npm install', trigger=['./app/package.json']),
  ]
)

# Apply K8s manifests
k8s_yaml([
  'deploy/k8s/namespace.yaml',
  'deploy/k8s/secrets.example.yaml',
  'deploy/k8s/app-stack.yaml',
])

# Tilt automatically matches docker_build image names to K8s manifests.
# If images don't match, use k8s_image_json_path or set_image.

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
