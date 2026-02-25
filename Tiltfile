# FinMind Tiltfile — Local K8s Development Workflow
# ─────────────────────────────────────────────────
# Prerequisites:
#   1. Install Tilt: https://docs.tilt.dev/install.html
#   2. A local K8s cluster (minikube, kind, Docker Desktop, etc.)
#   3. kubectl configured to point at your local cluster
#
# Run:
#   tilt up
#
# Dashboard: http://localhost:10350

# ============================================================
# Configuration
# ============================================================

load('ext://namespace', 'namespace_create')

# Create namespace if it doesn't exist
namespace_create('finmind')

# ============================================================
# Docker Builds with Live Update
# ============================================================

# Backend: Flask API with hot-reload via live_update
docker_build(
    'finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        run('pip install -r requirements.txt',
            trigger=['./packages/backend/requirements.txt']),
    ],
)

# Frontend: React/Vite dev server for live development
docker_build(
    'finmind-frontend-dev',
    context='./app',
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
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        sync('./app/index.html', '/app/index.html'),
        run('npm install', trigger=['./app/package.json']),
    ],
)

# ============================================================
# Infrastructure: PostgreSQL & Redis
# ============================================================

k8s_yaml(blob("""
apiVersion: v1
kind: Secret
metadata:
  name: finmind-secrets
  namespace: finmind
type: Opaque
stringData:
  POSTGRES_USER: finmind
  POSTGRES_PASSWORD: finmind
  POSTGRES_DB: finmind
  JWT_SECRET: dev-secret-change-in-production
  GEMINI_API_KEY: ""
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
---
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
---
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
          image: redis:7-alpine
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
"""))

k8s_resource('postgres', labels=['infra'], port_forwards='5432:5432')
k8s_resource('redis', labels=['infra'], port_forwards='6379:6379')

# ============================================================
# Backend (Flask API)
# ============================================================

k8s_yaml(blob("""
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
        - name: init-db
          image: finmind-backend
          command: ["python", "-m", "flask", "--app", "wsgi:app", "init-db"]
          env:
            - name: DATABASE_URL
              value: postgresql+psycopg2://finmind:finmind@postgres:5432/finmind
            - name: REDIS_URL
              value: redis://redis:6379/0
            - name: JWT_SECRET
              value: dev-secret-change-in-production
      containers:
        - name: backend
          image: finmind-backend
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              value: postgresql+psycopg2://finmind:finmind@postgres:5432/finmind
            - name: REDIS_URL
              value: redis://redis:6379/0
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: JWT_SECRET
            - name: GEMINI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: finmind-secrets
                  key: GEMINI_API_KEY
            - name: LOG_LEVEL
              value: DEBUG
            - name: GEMINI_MODEL
              value: gemini-1.5-flash
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 20
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
"""))

k8s_resource(
    'backend',
    labels=['app'],
    port_forwards='8000:8000',
    resource_deps=['postgres', 'redis'],
)

# ============================================================
# Frontend (React/Vite Dev Server)
# ============================================================

k8s_yaml(blob("""
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
              value: http://localhost:8000
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
"""))

k8s_resource(
    'frontend',
    labels=['app'],
    port_forwards='5173:5173',
    resource_deps=['backend'],
)

# ============================================================
# Tilt UI Configuration
# ============================================================

# Allow selecting which resources to run
config.define_string_list("to-run", args=True)
cfg = config.parse()
groups = cfg.get("to-run", [])
if groups:
    config.set_enabled_resources(groups)
