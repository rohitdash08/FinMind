#!/usr/bin/env bash
set -euo pipefail

echo "=== FinMind Universal Deploy Script ==="
echo "Select target platform:"
echo "1) Docker Compose (local)"
echo "2) Kubernetes (k8s)"
echo "3) Tilt (dev)"
echo "4) Railway"
echo "5) Heroku"
echo "6) DigitalOcean"
echo "7) Render"
echo "8) Fly.io"
echo "9) AWS ECS"
echo "10) GCP Cloud Run"
echo "11) Azure Container Instances"
echo ""
read -rp "Enter choice [1-11]: " choice

case "$choice" in
  1)
    docker compose up --build
    ;;
  2)
    kubectl apply -f deploy/k8s/namespace.yaml
    kubectl apply -f deploy/k8s/secrets.yaml
    kubectl apply -f deploy/k8s/app-stack.yaml
    kubectl apply -f deploy/k8s/monitoring-stack.yaml
    ;;
  3)
    tilt up
    ;;
  4)
    railway up
    ;;
  5)
    git push heroku main
    heroku open
    ;;
  6)
    doctl apps create --spec deploy/digitalocean/app.yaml
    ;;
  7)
    echo "Connect repo at https://dashboard.render.com and use deploy/render/render.yaml"
    ;;
  8)
    fly launch --copy-config --no-deploy
    fly deploy
    ;;
  9)
    bash deploy/aws/deploy.sh
    ;;
  10)
    bash deploy/gcp/deploy-cloudrun.sh
    ;;
  11)
    bash deploy/azure/deploy.sh
    ;;
  *)
    echo "Invalid choice"
    exit 1
    ;;
esac
