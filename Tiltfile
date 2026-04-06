# FinMind Tiltfile - Local Kubernetes Development with Tilt
# Usage: tilt up

load("ext://namespace", "namespace_create", "namespace_inject")
load("ext://helm_resource", "helm_resource", "helm_repo")

allow_k8s_contexts(k8s_context())

namespace_create("finmind")

docker_build(
    "finmind-backend",
    context="./packages/backend",
    dockerfile="./packages/backend/Dockerfile",
    live_update=[
        sync("./packages/backend/app", "/app/app"),
        sync("./packages/backend/wsgi.py", "/app/wsgi.py"),
        run("pip install -r requirements.txt", trigger=["./packages/backend/requirements.txt"]),
    ],
)

docker_build(
    "finmind-frontend",
    context="./app",
    dockerfile="./app/Dockerfile",
    live_update=[
        sync("./app/src", "/app/src"),
        sync("./app/public", "/app/public"),
        sync("./app/index.html", "/app/index.html"),
        run("npm install", trigger=["./app/package.json"]),
    ],
)

helm_resource(
    "finmind",
    chart="./deploy/helm/finmind",
    namespace="finmind",
    flags=[
        "--set", "backend.image.repository=finmind-backend",
        "--set", "backend.image.tag=latest",
        "--set", "frontend.image.repository=finmind-frontend",
        "--set", "frontend.image.tag=latest",
        "--set", "backend.autoscaling.enabled=false",
        "--set", "frontend.autoscaling.enabled=false",
        "--set", "ingress.enabled=false",
        "--set", "monitoring.enabled=false",
    ],
    image_deps=["finmind-backend", "finmind-frontend"],
    image_keys=[
        ("backend.image.repository", "backend.image.tag"),
        ("frontend.image.repository", "frontend.image.tag"),
    ],
)

k8s_resource(
    "finmind-backend",
    port_forwards=[port_forward(8000, 8000, name="Backend API")],
    labels=["app"],
)

k8s_resource(
    "finmind-frontend",
    port_forwards=[port_forward(5173, 80, name="Frontend")],
    labels=["app"],
)

k8s_resource(
    "finmind-postgres",
    port_forwards=[port_forward(5432, 5432, name="PostgreSQL")],
    labels=["infra"],
)

k8s_resource(
    "finmind-redis",
    port_forwards=[port_forward(6379, 6379, name="Redis")],
    labels=["infra"],
)

print("==================================================")
print("  FinMind Local K8s Dev Environment (Tilt)")
print("  Frontend:  http://localhost:5173")
print("  Backend:   http://localhost:8000")
print("  Health:    http://localhost:8000/health")
print("==================================================")
