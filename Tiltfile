# FinMind - Tilt Development Environment
# Usage: tilt up
# Prerequisites: Docker, kubectl, a local K8s cluster (minikube/kind/k3d)

# ============================================================
# Configuration
# ============================================================

load('ext://helm_resource', 'helm_resource', 'helm_repo')
load('ext://namespace', 'namespace_create')

# Create namespace
namespace_create('finmind-dev')

# ============================================================
# Infrastructure: PostgreSQL & Redis
# ============================================================

# PostgreSQL
k8s_yaml(blob("""
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: finmind-dev
spec:
  ports:
    - port: 5432
  selector:
    app: postgres
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: finmind-dev
spec:
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
          env:
            - name: POSTGRES_USER
              value: finmind
            - name: POSTGRES_PASSWORD
              value: finmind
            - name: POSTGRES_DB
              value: finmind
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "finmind"]
            initialDelaySeconds: 5
            periodSeconds: 5
"""))

k8s_resource('postgres', labels=['infra'], port_forwards='5432:5432')

# Redis
k8s_yaml(blob("""
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: finmind-dev
spec:
  ports:
    - port: 6379
  selector:
    app: redis
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: finmind-dev
spec:
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
          image: redis:7-alpine
          ports:
            - containerPort: 6379
"""))

k8s_resource('redis', labels=['infra'], port_forwards='6379:6379')

# ============================================================
# Backend (Flask API)
# ============================================================

docker_build(
    'finmind-api',
    context='.',
    dockerfile='packages/backend/Dockerfile',
    live_update=[
        sync('packages/backend/app', '/app/app'),
        sync('packages/backend/wsgi.py', '/app/wsgi.py'),
        run('pip install -r /app/requirements.txt', trigger='packages/backend/requirements.txt'),
    ],
)

k8s_yaml(blob("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: finmind-api
  namespace: finmind-dev
spec:
  selector:
    matchLabels:
      app: finmind-api
  template:
    metadata:
      labels:
        app: finmind-api
    spec:
      initContainers:
        - name: init-db
          image: finmind-api
          command: ["python", "-m", "flask", "--app", "wsgi:app", "init-db"]
          env:
            - name: DATABASE_URL
              value: postgresql+psycopg2://finmind:finmind@postgres:5432/finmind
            - name: REDIS_URL
              value: redis://redis:6379/0
            - name: JWT_SECRET
              value: dev-secret-change-in-production
      containers:
        - name: api
          image: finmind-api
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              value: postgresql+psycopg2://finmind:finmind@postgres:5432/finmind
            - name: REDIS_URL
              value: redis://redis:6379/0
            - name: JWT_SECRET
              value: dev-secret-change-in-production
            - name: LOG_LEVEL
              value: DEBUG
            - name: FLASK_DEBUG
              value: "1"
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: finmind-api
  namespace: finmind-dev
spec:
  ports:
    - port: 8000
  selector:
    app: finmind-api
"""))

k8s_resource(
    'finmind-api',
    labels=['app'],
    port_forwards='8000:8000',
    resource_deps=['postgres', 'redis'],
)

# ============================================================
# Frontend (React/Vite)
# ============================================================

# For dev, use live-reload with Vite dev server
docker_build(
    'finmind-web-dev',
    context='app',
    dockerfile_contents="""
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV VITE_API_URL=http://localhost:8000
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
""",
    live_update=[
        sync('app/src', '/app/src'),
        sync('app/public', '/app/public'),
        sync('app/index.html', '/app/index.html'),
        run('npm install', trigger='app/package.json'),
    ],
)

k8s_yaml(blob("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: finmind-web
  namespace: finmind-dev
spec:
  selector:
    matchLabels:
      app: finmind-web
  template:
    metadata:
      labels:
        app: finmind-web
    spec:
      containers:
        - name: web
          image: finmind-web-dev
          ports:
            - containerPort: 5173
          env:
            - name: VITE_API_URL
              value: http://localhost:8000
---
apiVersion: v1
kind: Service
metadata:
  name: finmind-web
  namespace: finmind-dev
spec:
  ports:
    - port: 5173
  selector:
    app: finmind-web
"""))

k8s_resource(
    'finmind-web',
    labels=['app'],
    port_forwards='5173:5173',
    resource_deps=['finmind-api'],
)

# ============================================================
# Tilt UI Configuration
# ============================================================

# Group resources for Tilt dashboard
config.define_string_list("to-run", args=True)
cfg = config.parse()
groups = cfg.get("to-run", [])
if groups:
    config.set_enabled_resources(groups)
