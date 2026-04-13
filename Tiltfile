# FinMind Tiltfile for local Kubernetes development

# Backend
docker_build('finmind/backend', './packages/backend',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        run('pip install -r requirements.txt', trigger=['./packages/backend/requirements.txt']),
    ])

# Frontend
docker_build('finmind/frontend', './app',
    live_update=[
        sync('./app/src', '/app/src'),
    ])

# Apply K8s manifests
k8s_yaml([
    'deploy/kubernetes/namespace.yaml',
    'deploy/kubernetes/postgres.yaml',
    'deploy/kubernetes/redis.yaml',
    'deploy/kubernetes/backend.yaml',
    'deploy/kubernetes/frontend.yaml',
])

# Port forwards
k8s_resource('backend', port_forwards='8000:8000')
k8s_resource('frontend', port_forwards='3000:80')
k8s_resource('postgres', port_forwards='5432:5432')
