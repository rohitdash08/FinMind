#!/usr/bin/env sh
set -eu

if [ ! -f deploy/k8s/secrets.yaml ]; then
  echo "WARNING: deploy/k8s/secrets.yaml not found — copying from secrets.example.yaml."
  echo "         Edit deploy/k8s/secrets.yaml with real credentials before production use, then re-run this script."
  cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
  exit 1
fi

kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/app-stack.yaml
kubectl apply -f deploy/k8s/monitoring-stack.yaml

echo "Kubernetes deployment applied to namespace: finmind"
