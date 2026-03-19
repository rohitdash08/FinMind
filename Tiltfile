# FinMind — Tiltfile for local Kubernetes development
# Prerequisites: Docker Desktop with K8s enabled (or kind/minikube), Tilt v0.33+
#
# Usage:
#   tilt up          # Start all services with live reload
#   tilt down        # Tear down (keeps volumes by default)
#   tilt down --delete-namespaces  # Full cleanup

load('ext://helm_resource', 'helm_resource', 'helm_repo')
load('ext://namespace', 'namespace_create', 'namespace_inject')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGISTRY = os.environ.get('TILT_REGISTRY', 'localhost:5005')
NAMESPACE = 'finmind-dev'

# ---------------------------------------------------------------------------
# Namespace
# ---------------------------------------------------------------------------
namespace_create(NAMESPACE)

# ---------------------------------------------------------------------------
# Backend — live-reload Python with hot restart on file change
# ---------------------------------------------------------------------------
docker_build(
    REGISTRY + '/finmind-backend',
    context='./packages/backend',
    dockerfile='./packages/backend/Dockerfile',
    live_update=[
        sync('./packages/backend/app', '/app/app'),
        sync('./packages/backend/wsgi.py', '/app/wsgi.py'),
        run(
            'pip install -r /app/requirements.txt',
            trigger=['./packages/backend/requirements.txt'],
        ),
        restart_container(),
    ],
)

k8s_yaml(namespace_inject(read_file('./deploy/k8s/namespace.yaml'), NAMESPACE))
k8s_yaml(namespace_inject(blob("""
apiVersion: v1
kind: Secret
metadata:
  name: finmind-secrets
type: Opaque
stringData:
  POSTGRES_USER: finmind
  POSTGRES_PASSWORD: finmind_dev
  POSTGRES_DB: finmind
  JWT_SECRET: dev-only-jwt-secret-change-in-prod
  GEMINI_API_KEY: ""
  DATABASE_URL: "postgresql+psycopg2://finmind:finmind_dev@postgres:5432/finmind"
"""), NAMESPACE))

k8s_yaml(namespace_inject(blob("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: finmind-config
data:
  LOG_LEVEL: DEBUG
  GEMINI_MODEL: gemini-1.5-flash
  REDIS_URL: redis://redis:6379/0
  PROMETHEUS_MULTIPROC_DIR: /tmp/prometheus_multiproc
"""), NAMESPACE))

# ---------------------------------------------------------------------------
# Infrastructure — Postgres + Redis (local PVCs, fast restart)
# ---------------------------------------------------------------------------
k8s_yaml(namespace_inject(blob("""
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data-dev
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 2Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
spec:
  replicas: 1
  strategy:
    type: Recreate
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
          envFrom:
            - secretRef:
                name: finmind-secrets
          ports:
            - containerPort: 5432
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "finmind", "-d", "finmind"]
            initialDelaySeconds: 3
            periodSeconds: 3
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-data-dev
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
"""), NAMESPACE))

k8s_yaml(namespace_inject(blob("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
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
          args: ["--save", ""]
          ports:
            - containerPort: 6379
          readinessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 2
            periodSeconds: 3
---
apiVersion: v1
kind: Service
metadata:
  name: redis
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
"""), NAMESPACE))

# ---------------------------------------------------------------------------
# Backend deployment
# ---------------------------------------------------------------------------
k8s_yaml(namespace_inject(blob("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
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
          image: """ + REGISTRY + """/finmind-backend
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: finmind-secrets
            - configMapRef:
                name: finmind-config
          command:
            - sh
            - -c
            - |
              python -m flask --app wsgi:app init-db &&
              rm -rf $PROMETHEUS_MULTIPROC_DIR && mkdir -p $PROMETHEUS_MULTIPROC_DIR &&
              exec gunicorn --reload --workers=1 --threads=4 --bind 0.0.0.0:8000 wsgi:app
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 8
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: backend
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
"""), NAMESPACE))

# ---------------------------------------------------------------------------
# Frontend — live-reload Vite dev server
# ---------------------------------------------------------------------------
docker_build(
    REGISTRY + '/finmind-frontend-dev',
    context='./app',
    dockerfile_contents="""
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
""",
    live_update=[
        sync('./app/src', '/app/src'),
        sync('./app/public', '/app/public'),
        run('npm ci', trigger=['./app/package.json', './app/package-lock.json']),
    ],
)

k8s_yaml(namespace_inject(blob("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
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
          image: """ + REGISTRY + """/finmind-frontend-dev
          ports:
            - containerPort: 5173
          env:
            - name: CHOKIDAR_USEPOLLING
              value: "true"
          readinessProbe:
            httpGet:
              path: /
              port: 5173
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
spec:
  selector:
    app: frontend
  ports:
    - port: 5173
      targetPort: 5173
"""), NAMESPACE))

# ---------------------------------------------------------------------------
# Port-forwards (auto-opened in browser by Tilt)
# ---------------------------------------------------------------------------
k8s_resource('backend',  port_forwards='8000:8000',  labels=['app'])
k8s_resource('frontend', port_forwards='5173:5173',  labels=['app'])
k8s_resource('postgres', port_forwards='5432:5432',  labels=['infra'])
k8s_resource('redis',    port_forwards='6379:6379',  labels=['infra'])

# ---------------------------------------------------------------------------
# Resource dependencies (Tilt waits for readiness before next layer)
# ---------------------------------------------------------------------------
k8s_resource('backend',  resource_deps=['postgres', 'redis'])
k8s_resource('frontend', resource_deps=['backend'])
