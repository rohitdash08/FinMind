# Tilt workflow

1. Ensure Docker Desktop, kind/minikube, Helm, and Tilt are installed.
2. Start a local Kubernetes cluster.
3. Run `tilt up` from the repository root.
4. Use `scripts/validate-deploy.sh` against the port-forwards once the stack is healthy.
