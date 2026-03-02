# Tiltfile for FinMind Universal Deployment
# Part of $1000 Bounty Requirement

# 1. Build the frontend/backend image
docker_build('finmind-app', '.', dockerfile='app/Dockerfile')

# 2. Deploy to Kubernetes (using the refactored manifests)
k8s_yaml([
    'deploy/k8s/namespace.yaml',
    'deploy/k8s/secrets.example.yaml', # Note: User must fill this
    'deploy/k8s/app-stack.yaml',
    'deploy/k8s/monitoring-stack.yaml'
])

# 3. Port forwarding for local dev access
k8s_resource('app', port_forwards=8000)
k8s_resource('redis', port_forwards=6379)
k8s_resource('postgres', port_forwards=5432)

# 4. Success Message
print("FinMind is now launching in your local K8s cluster via Tilt!")
