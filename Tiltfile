# FinMind Tiltfile for local Kubernetes development
# Prerequisites: Docker Desktop/Rancher Desktop with Kubernetes, Tilt installed
# Run: tilt up

# Configuration
load('ext://restart_process', 'docker_build_with_restart')

# --- Configuration ---
config.define_bool("production")
cfg = config.parse()
production = cfg.get("production", False)

# --- Build Backend Image ---
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

# --- Build Frontend Image ---
docker_build(
    'finmind-frontend',
    context='./app',
    dockerfile='./app/Dockerfile',
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        run('npm install', trigger=['./app/package.json']),
    ],
)

# --- Kubernetes Resources ---
# Apply namespace first
k8s_yaml('deploy/k8s/namespace.yaml')

# Apply secrets (copy from example and fill in)
if os.path.exists('deploy/k8s/secrets.yaml'):
    k8s_yaml('deploy/k8s/secrets.yaml')
else:
    warn('deploy/k8s/secrets.yaml not found! Copy from secrets.example.yaml and fill in values.')
    k8s_yaml('deploy/k8s/secrets.example.yaml')

# Apply main stack
k8s_yaml('deploy/k8s/app-stack.yaml')

# --- Resource Configuration ---
k8s_resource(
    'postgres',
    labels=['database'],
    port_forwards='5432:5432',
)

k8s_resource(
    'redis',
    labels=['database'],
    port_forwards='6379:6379',
)

k8s_resource(
    'backend',
    labels=['app'],
    port_forwards='8000:8000',
    resource_deps=['postgres', 'redis'],
)

k8s_resource(
    'nginx',
    labels=['app'],
    port_forwards='8080:80',
    resource_deps=['backend'],
)

# --- Optional: Monitoring Stack ---
if production or os.path.exists('deploy/k8s/monitoring-stack.yaml'):
    k8s_yaml('deploy/k8s/monitoring-stack.yaml')
    
    k8s_resource(
        'prometheus',
        labels=['monitoring'],
        port_forwards='9090:9090',
    )
    
    k8s_resource(
        'grafana',
        labels=['monitoring'],
        port_forwards='3000:3000',
    )

# --- Local Development Helpers ---
local_resource(
    'backend-tests',
    cmd='docker compose exec backend pytest tests/ -v',
    labels=['test'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

local_resource(
    'frontend-tests',
    cmd='docker compose exec frontend-dev npm test',
    labels=['test'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

# --- Quick Commands ---
print("""
╔═══════════════════════════════════════════════════════════╗
║               FinMind Local Development                  ║
╠═══════════════════════════════════════════════════════════╣
║  Backend:   http://localhost:8000                        ║
║  Frontend:  http://localhost:5173 (if using compose)     ║
║  Nginx:     http://localhost:8080                        ║
║  Postgres:  localhost:5432                               ║
║  Redis:     localhost:6379                               ║
╠═══════════════════════════════════════════════════════════╣
║  Monitoring (if enabled):                                ║
║  Grafana:   http://localhost:3000                        ║
║  Prometheus: http://localhost:9090                       ║
╚═══════════════════════════════════════════════════════════╝
""")
