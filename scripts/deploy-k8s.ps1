Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml

Write-Host "Kubernetes deployment applied to namespace: finmind"
