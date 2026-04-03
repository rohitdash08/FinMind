# FinMind Tilt Configuration - Local K8s Development

# Build backend image
docker_build(
    'finmind/backend',
    context='packages/backend',
    dockerfile='packages/backend/Dockerfile',
    live_update=[
        sync('packages/backend/app', '/app/app'),
    ]
)

# Render Helm chart and apply
k8s_yaml(helm(
    'deploy/helm/finmind',
    values=['./deploy/helm/finmind/values.yaml'],
))

# Port forwards
k8s_resource(
    'finmind-backend',
    port_forwards='8000',
)

k8s_resource(
    'finmind-postgres',
    port_forwards='5432',
)

k8s_resource(
    'finmind-redis',
    port_forwards='6379',
)

# Disable telemetry
disable_snapshots()
