# FinMind Tiltfile - One-click local K8s development

# 1. Build images
docker_build('finmind-frontend', './app', 
             dockerfile='./app/Dockerfile',
             live_update=[
                 sync('./app/src', '/app/src'),
             ])

docker_build('finmind-backend', './packages/backend',
             dockerfile='./packages/backend/Dockerfile',
             live_update=[
                 sync('./packages/backend/app', '/app/app'),
             ])

# 2. Deploy to K8s
k8s_yaml([
    './deploy/k8s/namespace.yaml',
    './deploy/k8s/app-stack.yaml',
    './deploy/k8s/monitoring-stack.yaml'
])

# 3. Port forwards
k8s_resource('finmind-frontend', port_forwards=3000)
k8s_resource('finmind-backend', port_forwards=8000)

print("FinMind is starting up. Frontend at http://localhost:3000, Backend at http://localhost:8000")
