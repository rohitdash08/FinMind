#!/usr/bin/env sh
set -eu

kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml

echo "Kubernetes deployment applied to namespace: finmind"
