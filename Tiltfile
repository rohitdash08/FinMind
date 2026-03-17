# ============================================================================
# FinMind Tiltfile - Local Kubernetes Development
# ============================================================================
# Usage:
#   1. Start local K8s cluster (minikube, kind, Docker Desktop)
#   2. Run: tilt up
#   3. Access: http://localhost:5173 (frontend), http://localhost:8000 (backend)
# ============================================================================

# Load extensions
load('ext://restart_process', 'docker_build_with_restart')
load('ext://namespace', 'namespace_create')

# ============================================================================
# Configuration
# ============================================================================
config.define_string('namespace', args=False)
config.define_bool('production', args=False)
cfg = config.parse()

NAMESPACE = cfg.get('namespace', 'finmind-dev')
IS_PROD = cfg.get('production', False)

# Create namespace
namespace_create(NAMESPACE)

# ============================================================================
# Docker Builds with Live Reload
# ============================================================================

# Backend - Python Flask with hot reload
docker_build_with_restart(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile.dev',
    entrypoint=[
        'sh', '-c',
        '''
        python -m flask --app wsgi:app init-db
        gunicorn --reload --workers=1 --threads=2 --bind 0.0.0.0:8000 wsgi:app
        '''
    ],
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
    ],
)

# Frontend - React Vite with HMR
docker_build_with_restart(
    'finmind-frontend-dev',
    context='./app',
    dockerfile='./app/Dockerfile.dev',
    entrypoint=['npm', 'run', 'dev', '--', '--host', '0.0.0.0', '--port', '5173'],
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/index.html', '/app/index.html'),
        run('cd /app && npm install', trigger=['./app/package.json']),
    ],
)

# ============================================================================
# Kubernetes Resources
# ============================================================================

# Apply base infrastructure
k8s_yaml([
    'deploy/tilt/namespace.yaml',
    'deploy/tilt/secrets.yaml',
    'deploy/tilt/postgres.yaml',
    'deploy/tilt/redis.yaml',
])

# Apply application
k8s_yaml([
    'deploy/tilt/backend.yaml',
    'deploy/tilt/frontend.yaml',
])

# ============================================================================
# Resource Configuration
# ============================================================================

# PostgreSQL
k8s_resource(
    'postgres',
    port_forwards=['5432:5432'],
    labels=['database'],
)

# Redis
k8s_resource(
    'redis',
    port_forwards=['6379:6379'],
    labels=['database'],
)

# Backend API
k8s_resource(
    'backend',
    port_forwards=['8000:8000'],
    resource_deps=['postgres', 'redis'],
    labels=['app'],
)

# Frontend
k8s_resource(
    'frontend',
    port_forwards=['5173:5173'],
    resource_deps=['backend'],
    labels=['app'],
)

# ============================================================================
# Local Resource: Database UI (optional)
# ============================================================================
# Uncomment to add pgAdmin for database management
# local_resource(
#     'pgadmin',
#     serve_cmd='docker run --rm -p 5050:80 -e PGADMIN_DEFAULT_EMAIL=admin@local.dev -e PGADMIN_DEFAULT_PASSWORD=admin dpage/pgadmin4',
#     labels=['tools'],
# )

# ============================================================================
# Buttons for common operations
# ============================================================================

# Run backend tests
local_resource(
    'backend-tests',
    cmd='cd packages/backend && pytest -v',
    auto_init=False,
    labels=['tests'],
)

# Run frontend tests
local_resource(
    'frontend-tests',
    cmd='cd app && npm test',
    auto_init=False,
    labels=['tests'],
)

# Database migrations (manual trigger)
local_resource(
    'db-init',
    cmd='kubectl exec -n ' + NAMESPACE + ' deploy/backend -- python -m flask --app wsgi:app init-db',
    auto_init=False,
    labels=['database'],
)

# ============================================================================
# Display helpful links
# ============================================================================
print("""
╔══════════════════════════════════════════════════════════════════╗
║                    🧠 FinMind Development                        ║
╠══════════════════════════════════════════════════════════════════╣
║  Frontend:  http://localhost:5173                                ║
║  Backend:   http://localhost:8000                                ║
║  API Docs:  http://localhost:8000/docs (if enabled)              ║
║  Postgres:  localhost:5432                                       ║
║  Redis:     localhost:6379                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Tilt UI:   http://localhost:10350                               ║
╚══════════════════════════════════════════════════════════════════╝
""")
