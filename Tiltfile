# FinMind Tiltfile — Local Kubernetes Development Workflow
# Usage: tilt up
# Requirements: Docker, kubectl, a local K8s cluster (minikube, kind, Docker Desktop K8s)

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
load('ext://namespace', 'namespace_create', 'namespace_inject')
allow_k8s_contexts(['docker-desktop', 'minikube', 'kind-kind', 'kind-finmind'])
default_registry('localhost:5000')

# Fail fast if user accidentally points at a production cluster
if k8s_context() not in ['docker-desktop', 'minikube', 'kind-kind', 'kind-finmind']:
    fail('Refusing to run Tilt against non-local context: ' + k8s_context())

# ─────────────────────────────────────────────────────────────
# Namespace
# ─────────────────────────────────────────────────────────────
namespace_create('finmind')

# ─────────────────────────────────────────────────────────────
# Docker Builds with Live Update
# ─────────────────────────────────────────────────────────────

# Backend: Python Flask + Gunicorn
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        # Sync Python source files for hot-reload (gunicorn --reload)
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        # Restart gunicorn if requirements change
        run('pip install -r /app/requirements.txt',
            trigger=['./packages/backend/requirements.txt']),
    ],
)

# Frontend: React + Vite (Nginx for production, dev server for Tilt)
docker_build(
    'finmind-frontend-dev',
    context='./app',
    dockerfile_contents='''
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
''',
    live_update=[
        # Sync source files — Vite HMR handles the rest
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        sync('./app/index.html', '/app/index.html'),
        # Reinstall deps if package.json changes
        run('cd /app && npm install',
            trigger=['./app/package.json', './app/package-lock.json']),
    ],
)

# ─────────────────────────────────────────────────────────────
# Kubernetes Resources — Inline YAML for Dev
# ─────────────────────────────────────────────────────────────

# Secrets (dev-only, not for production)
k8s_yaml(blob('''
apiVersion: v1
kind: Secret
metadata:
  name: finmind-secrets
  namespace: finmind
type: Opaque
stringData:
  POSTGRES_USER: finmind
  POSTGRES_PASSWORD: finmind-dev
  POSTGRES_DB: finmind
  JWT_SECRET: dev-jwt-secret-not-for-production
  GRAFANA_ADMIN_USER: admin
  GRAFANA_ADMIN_PASSWORD: admin
  GEMINI_API_KEY: ""
'''))

# ConfigMap
k8s_yaml(blob('''
apiVersion: v1
kind: ConfigMap
metadata:
  name: finmind-config
  namespace: finmind
data:
  LOG_LEVEL: DEBUG
  GEMINI_MODEL: gemini-1.5-flash
  REDIS_URL: "redis://redis:6379/0"
  VITE_API_URL: "http://localhost:8000"
'''))

# PostgreSQL
k8s_yaml(blob('''
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
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "finmind"]
            initialDelaySeconds: 5
            periodSeconds: 5
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
'''))

# Redis
k8s_yaml(blob('''
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
          readinessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 3
            periodSeconds: 5
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
'''))

# Backend
k8s_yaml(blob('''
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
      initContainers:
        - name: wait-for-postgres
          image: busybox:1.36
          command: ["sh", "-c", "until nc -z postgres 5432; do sleep 2; done"]
        - name: init-db
          image: finmind-backend
          command: ["python", "-m", "flask", "--app", "wsgi:app", "init-db"]
          env:
            - name: POSTGRES_USER
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_USER}}
            - name: POSTGRES_PASSWORD
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_PASSWORD}}
            - name: POSTGRES_DB
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_DB}}
            - name: JWT_SECRET
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: JWT_SECRET}}
            - name: GEMINI_API_KEY
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: GEMINI_API_KEY}}
            - name: DATABASE_URL
              value: "postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)"
            - name: REDIS_URL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: REDIS_URL}}
            - name: GEMINI_MODEL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: GEMINI_MODEL}}
            - name: LOG_LEVEL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: LOG_LEVEL}}
      containers:
        - name: backend
          image: finmind-backend
          ports:
            - containerPort: 8000
          env:
            - name: POSTGRES_USER
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_USER}}
            - name: POSTGRES_PASSWORD
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_PASSWORD}}
            - name: POSTGRES_DB
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: POSTGRES_DB}}
            - name: JWT_SECRET
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: JWT_SECRET}}
            - name: GEMINI_API_KEY
              valueFrom: {secretKeyRef: {name: finmind-secrets, key: GEMINI_API_KEY}}
            - name: DATABASE_URL
              value: "postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)"
            - name: REDIS_URL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: REDIS_URL}}
            - name: GEMINI_MODEL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: GEMINI_MODEL}}
            - name: LOG_LEVEL
              valueFrom: {configMapKeyRef: {name: finmind-config, key: LOG_LEVEL}}
          command:
            - sh
            - -c
            - |
              export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
              rm -rf $PROMETHEUS_MULTIPROC_DIR && mkdir -p $PROMETHEUS_MULTIPROC_DIR
              exec gunicorn --reload --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app
          readinessProbe:
            httpGet: {path: /health, port: 8000}
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
'''))

# Frontend (dev mode with Vite HMR)
k8s_yaml(blob('''
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
          image: finmind-frontend-dev
          ports:
            - containerPort: 5173
          env:
            - name: VITE_API_URL
              value: "http://localhost:8000"
          readinessProbe:
            httpGet: {path: /, port: 5173}
            initialDelaySeconds: 15
            periodSeconds: 5
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
'''))

# ─────────────────────────────────────────────────────────────
# Resource Configuration
# ─────────────────────────────────────────────────────────────

# Dependency ordering: postgres -> redis -> backend -> frontend
k8s_resource('postgres', labels=['data'])
k8s_resource('redis', labels=['data'])
k8s_resource('backend',
    labels=['app'],
    resource_deps=['postgres', 'redis'],
    port_forwards=['8000:8000'],
)
k8s_resource('frontend',
    labels=['app'],
    resource_deps=['backend'],
    port_forwards=['5173:5173'],
)

# ─────────────────────────────────────────────────────────────
# Manual Trigger Buttons
# ─────────────────────────────────────────────────────────────
local_resource(
    'run-backend-tests',
    cmd='cd packages/backend && python -m pytest tests/ -v --tb=short 2>&1 || true',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

local_resource(
    'run-frontend-tests',
    cmd='cd app && npm test -- --watchAll=false 2>&1 || true',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

local_resource(
    'smoke-test',
    cmd='deploy/scripts/smoke-test.sh http://localhost:8000 http://localhost:5173 2>&1 || true',
    labels=['dev'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    resource_deps=['backend', 'frontend'],
)
