allow_k8s_contexts(["kind-kind", "kind-finmind", "minikube", "docker-desktop"])

local("test -f deploy/k8s/secrets.yaml || cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml")

docker_build(
    "ghcr.io/rohitdash08/finmind-backend",
    "packages/backend",
    live_update=[
        sync("packages/backend/app", "/app/app"),
        sync("packages/backend/tests", "/app/tests"),
        sync("packages/backend/wsgi.py", "/app/wsgi.py"),
    ],
)

k8s_yaml([
    "deploy/k8s/namespace.yaml",
    "deploy/k8s/secrets.yaml",
    "deploy/k8s/app-stack.yaml",
    "deploy/k8s/monitoring-stack.yaml",
])

k8s_resource(
    "backend",
    port_forwards=["8000:8000"],
    resource_deps=["postgres", "redis"],
)

k8s_resource("nginx", port_forwards=["8080:80"], resource_deps=["backend"])
k8s_resource("grafana", port_forwards=["3000:3000"])
k8s_resource("prometheus", port_forwards=["9090:9090"])
k8s_resource("loki", port_forwards=["3100:3100"])

local_resource(
    "frontend-dev",
    cmd="cd app && npm install",
    serve_cmd="cd app && npm run dev -- --host 0.0.0.0 --port 5173",
    deps=["app/package.json", "app/package-lock.json", "app/src", "app/index.html"],
    resource_deps=["backend"],
)
