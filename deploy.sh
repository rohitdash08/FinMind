#!/bin/bash
# deploy.sh - Universal one-click deployment for FinMind
# Usage: ./deploy.sh [platform]
# Platforms: railway, heroku, render, fly, digitalocean, aws, gcp, azure, k8s, docker

set -e

PLATFORM="${1:-docker}"
APP_NAME="finmind"

echo "FinMind Universal Deployment"
echo "Platform: $PLATFORM"
echo "================================"

case "$PLATFORM" in
  docker)
    echo "Starting with Docker Compose..."
    docker-compose up -d
    echo "Done! Frontend: http://localhost:3000 | Backend: http://localhost:8000"
    ;;

  k8s|kubernetes)
    echo "Deploying to Kubernetes with Helm..."
    kubectl create namespace finmind --dry-run=client -o yaml | kubectl apply -f -
    helm upgrade --install finmind ./deploy/helm \
      --namespace finmind \
      --create-namespace \
      --values ./deploy/helm/values.yaml \
      --wait
    echo "Done! Run: kubectl port-forward svc/finmind-frontend 3000:3000 -n finmind"
    ;;

  railway)
    echo "Deploying to Railway..."
    command -v railway >/dev/null 2>&1 || npm install -g @railway/cli
    railway login
    railway up
    echo "Done! Check Railway dashboard for URL."
    ;;

  heroku)
    echo "Deploying to Heroku..."
    command -v heroku >/dev/null 2>&1 || curl https://cli-assets.heroku.com/install.sh | sh
    heroku create $APP_NAME 2>/dev/null || true
    heroku addons:create heroku-postgresql:mini -a $APP_NAME 2>/dev/null || true
    heroku addons:create heroku-redis:mini -a $APP_NAME 2>/dev/null || true
    heroku container:push web -a $APP_NAME
    heroku container:release web -a $APP_NAME
    echo "Done! URL: https://$APP_NAME.herokuapp.com"
    ;;

  render)
    echo "Deploying to Render..."
    echo "Please connect your GitHub repo at https://render.com/new"
    echo "Use render.yaml for automatic configuration."
    ;;

  fly)
    echo "Deploying to Fly.io..."
    command -v flyctl >/dev/null 2>&1 || curl -L https://fly.io/install.sh | sh
    flyctl launch --name $APP_NAME --no-deploy 2>/dev/null || true
    flyctl deploy
    echo "Done! URL: https://$APP_NAME.fly.dev"
    ;;

  digitalocean|do)
    echo "Deploying to DigitalOcean App Platform..."
    command -v doctl >/dev/null 2>&1 || snap install doctl
    doctl apps create --spec deploy/do-app-spec.yaml
    echo "Done! Check DigitalOcean dashboard."
    ;;

  aws)
    echo "Deploying to AWS ECS Fargate..."
    aws ecr get-login-password | docker login --username AWS --password-stdin \
      $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
    docker-compose -f deploy/docker-compose.aws.yml push
    aws ecs update-service --cluster finmind --service finmind-backend --force-new-deployment
    echo "Done! Check AWS ECS console."
    ;;

  gcp)
    echo "Deploying to GCP Cloud Run..."
    gcloud builds submit --tag gcr.io/$(gcloud config get-value project)/finmind-backend ./app/backend
    gcloud run deploy finmind-backend \
      --image gcr.io/$(gcloud config get-value project)/finmind-backend \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated
    echo "Done! Check GCP Cloud Run console."
    ;;

  azure)
    echo "Deploying to Azure Container Apps..."
    az containerapp up \
      --name $APP_NAME \
      --resource-group finmind-rg \
      --location eastus \
      --environment finmind-env \
      --image finmind-backend:latest \
      --target-port 8000 \
      --ingress external
    echo "Done! Check Azure portal."
    ;;

  tilt)
    echo "Starting Tilt local dev environment..."
    command -v tilt >/dev/null 2>&1 || curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | bash
    tilt up
    ;;

  *)
    echo "Unknown platform: $PLATFORM"
    echo "Available: docker, k8s, railway, heroku, render, fly, digitalocean, aws, gcp, azure, tilt"
    exit 1
    ;;
esac
