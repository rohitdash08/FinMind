# FinMind Tilt Configuration
# Local Kubernetes development workflow

# Build backend image
docker_build(
    'finmind/backend',
    context='packages/backend',
    dockerfile='packages/backend/Dockerfile',
    live_update=[
        sync('packages/backend/app', '/app/app'),
    ]
)

# Apply Helm chart
k8s_yaml('deploy/helm/finmind')

# Port forwards
k8s_resource(
    'finmind-backend',
    port_forwards='8000',
)

# PostgreSQL
k8s_resource(
    'finmind-postgres',
    port_forwards='5432',
)

# Redis
k8s_resource(
    'finmind-redis',
    port_forwards='6379',
)

# Disable telemetry
disable_snapshots()
