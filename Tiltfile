# FinMind Tiltfile - Local Kubernetes Development
# Run with: tilt up

# Configuration
load('ext://namespace', 'namespace_create')
load('ext://helm_resource', 'helm_resource', 'helm_repo')

# Create namespace
namespace_create('finmind')

# ============================================================================
# Build Docker images with live reload
# ============================================================================

# Backend image with live sync
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

# Frontend image with live sync
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

# ============================================================================
# Deploy infrastructure (Postgres, Redis)
# ============================================================================

k8s_yaml(local('cat <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: finmind
---
apiVersion: v1
kind: Secret
metadata:
  name: finmind-secrets
  namespace: finmind
stringData:
  POSTGRES_USER: finmind
  POSTGRES_PASSWORD: finmind
  POSTGRES_DB: finmind
  JWT_SECRET: dev-jwt-secret-change-in-production
  GRAFANA_ADMIN_USER: admin
  GRAFANA_ADMIN_PASSWORD: admin
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: finmind-config
  namespace: finmind
data:
  LOG_LEVEL: DEBUG
  GEMINI_MODEL: gemini-1.5-flash
  REDIS_URL: redis://redis:6379/0
  VITE_API_URL: http://localhost:8000
EOF'))

# Postgres
k8s_yaml(local('cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: finmind
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16
          ports:
            - containerPort: 5432
          envFrom:
            - secretRef:
                name: finmind-secrets
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: finmind
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
EOF'))

k8s_resource('postgres', labels=['infra'])

# Redis
k8s_yaml(local('cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: finmind
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7
          ports:
            - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: finmind
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
EOF'))

k8s_resource('redis', labels=['infra'])

# ============================================================================
# Deploy Backend
# ============================================================================

k8s_yaml(local('cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: finmind
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: finmind-backend
          ports:
            - containerPort: 8000
          env:
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: POSTGRES_PASSWORD
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: POSTGRES_DB
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: JWT_SECRET
            - name: DATABASE_URL
              value: "postgresql+psycopg2://\$(POSTGRES_USER):\$(POSTGRES_PASSWORD)@postgres:5432/\$(POSTGRES_DB)"
            - name: REDIS_URL
              valueFrom:
                configMapKeyRef:
                  name: finmind-config
                  key: REDIS_URL
            - name: LOG_LEVEL
              valueFrom:
                configMapKeyRef:
                  name: finmind-config
                  key: LOG_LEVEL
          command:
            - sh
            - -c
            - |
              python -m flask --app wsgi:app init-db && \
              export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc && \
              rm -rf \$PROMETHEUS_MULTIPROC_DIR && \
              mkdir -p \$PROMETHEUS_MULTIPROC_DIR && \
              gunicorn --reload --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: finmind
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
EOF'))

k8s_resource(
    'backend',
    port_forwards='8000:8000',
    resource_deps=['postgres', 'redis'],
    labels=['app'],
)

# ============================================================================
# Deploy Frontend (dev mode with hot reload)
# ============================================================================

k8s_yaml(local('cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: finmind
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: node:20-alpine
          workingDir: /app
          ports:
            - containerPort: 5173
          env:
            - name: VITE_API_URL
              value: http://localhost:8000
            - name: CHOKIDAR_USEPOLLING
              value: "true"
          command:
            - sh
            - -c
            - npm install && npm run dev -- --host 0.0.0.0 --port 5173
          volumeMounts:
            - name: app-src
              mountPath: /app
      volumes:
        - name: app-src
          hostPath:
            path: ${PWD}/app
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: finmind
spec:
  selector:
    app: frontend
  ports:
    - port: 5173
      targetPort: 5173
EOF'))

k8s_resource(
    'frontend',
    port_forwards='5173:5173',
    resource_deps=['backend'],
    labels=['app'],
)

# ============================================================================
# Tilt UI Configuration
# ============================================================================

# Update settings
update_settings(
    max_parallel_updates=3,
    k8s_upsert_timeout_secs=120,
)

# Local resource for running tests
local_resource(
    'backend-tests',
    cmd='cd packages/backend && python -m pytest tests/ -v',
    deps=['packages/backend/tests', 'packages/backend/app'],
    labels=['tests'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

local_resource(
    'frontend-tests',
    cmd='cd app && npm test',
    deps=['app/src'],
    labels=['tests'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

# Print helpful info on startup
print("""
╔══════════════════════════════════════════════════════════════════╗
║                    FinMind Local Development                     ║
╠══════════════════════════════════════════════════════════════════╣
║  Frontend:  http://localhost:5173                                ║
║  Backend:   http://localhost:8000                                ║
║  API Docs:  http://localhost:8000/docs                           ║
╠══════════════════════════════════════════════════════════════════╣
║  Press 's' for live log streaming                                ║
║  Press 'r' to restart a resource                                 ║
║  Press 't' to run tests                                          ║
╚══════════════════════════════════════════════════════════════════╝
""")
