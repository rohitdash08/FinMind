#!/usr/bin/env bash
# FinMind — Universal One-Click Deploy Script
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "╔══════════════════════════════════════╗"
echo "║     FinMind Deployment Launcher      ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Select a deployment platform:"
echo ""
echo "  1)  Docker Compose (local)"
echo "  2)  Kubernetes (kubectl)"
echo "  3)  Helm (Kubernetes)"
echo "  4)  Railway"
echo "  5)  Heroku"
echo "  6)  DigitalOcean App Platform"
echo "  7)  DigitalOcean Droplet"
echo "  8)  Render"
echo "  9)  Fly.io"
echo "  10) AWS ECS (CloudFormation)"
echo "  11) GCP Cloud Run"
echo "  12) Azure Container Apps"
echo "  13) Netlify (frontend only)"
echo "  14) Vercel (frontend only)"
echo ""
read -rp "Enter choice [1-14]: " choice

case "$choice" in
  1)
    echo "Starting Docker Compose..."
    cd "$REPO_ROOT"
    [ ! -f .env ] && cp .env.example .env && echo "Created .env from .env.example"
    docker compose up -d
    echo "✅ Running! Frontend: http://localhost:5173 | Backend: http://localhost:8000/health"
    ;;
  2)
    echo "Deploying to Kubernetes..."
    bash "$REPO_ROOT/scripts/deploy-k8s.sh"
    ;;
  3)
    echo "Deploying with Helm..."
    helm upgrade --install finmind "$REPO_ROOT/deploy/helm/finmind" \
      --namespace finmind --create-namespace \
      --set secrets.jwtSecret="$(openssl rand -hex 32)" \
      --set secrets.postgresPassword="$(openssl rand -hex 16)"
    echo "✅ Helm release deployed!"
    ;;
  4)
    echo "Deploy to Railway:"
    echo "  1. Install Railway CLI: npm i -g @railway/cli"
    echo "  2. railway login && railway init"
    echo "  3. Add PostgreSQL and Redis plugins in dashboard"
    echo "  4. railway up"
    echo "See: deploy/railway/README.md"
    ;;
  5)
    echo "Deploy to Heroku:"
    echo "  Option A — One-click: Add Deploy to Heroku button in README"
    echo "  Option B — CLI:"
    echo "    heroku create finmind-app"
    echo "    heroku stack:set container"
    echo "    heroku addons:create heroku-postgresql:essential-0"
    echo "    heroku addons:create heroku-redis:mini"
    echo "    cp deploy/heroku/heroku.yml ."
    echo "    git push heroku main"
    ;;
  6)
    echo "Deploy to DigitalOcean App Platform:"
    echo "  doctl apps create --spec .do/app.yaml"
    echo "  Or use the DO dashboard and import from GitHub."
    ;;
  7)
    echo "Deploy to DigitalOcean Droplet:"
    echo "  On your droplet, run:"
    echo "  curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/droplet/setup.sh | bash"
    ;;
  8)
    echo "Deploy to Render:"
    echo "  1. Push render.yaml to your repo"
    echo "  2. Go to https://dashboard.render.com/blueprints"
    echo "  3. Connect your GitHub repo — Render auto-detects render.yaml"
    ;;
  9)
    echo "Deploying to Fly.io..."
    bash "$REPO_ROOT/deploy/fly/deploy.sh"
    ;;
  10)
    echo "Deploy to AWS ECS:"
    echo "  1. Build & push images to ECR"
    echo "  2. aws cloudformation deploy \\"
    echo "       --template-file deploy/aws/cloudformation.yaml \\"
    echo "       --stack-name finmind \\"
    echo "       --parameter-overrides VpcId=<vpc> SubnetIds=<subnets> \\"
    echo "         BackendImage=<ecr-uri> FrontendImage=<ecr-uri> \\"
    echo "         DatabaseUrl=<db-url> RedisUrl=<redis-url> JwtSecret=<secret> \\"
    echo "       --capabilities CAPABILITY_NAMED_IAM"
    ;;
  11)
    echo "Deploy to GCP Cloud Run:"
    echo "  1. Create secrets in Secret Manager:"
    echo "     gcloud secrets create finmind-database-url --data-file=-"
    echo "     gcloud secrets create finmind-redis-url --data-file=-"
    echo "     gcloud secrets create finmind-jwt-secret --data-file=-"
    echo "  2. Submit build:"
    echo "     gcloud builds submit --config deploy/gcp/cloudbuild.yaml"
    ;;
  12)
    echo "Deploy to Azure Container Apps:"
    echo "  az deployment group create \\"
    echo "    --resource-group finmind-rg \\"
    echo "    --template-file deploy/azure/main.bicep \\"
    echo "    --parameters backendImage=<acr-image> frontendImage=<acr-image> \\"
    echo "      databaseUrl=<db-url> redisUrl=<redis-url> jwtSecret=<secret>"
    ;;
  13)
    echo "Deploy frontend to Netlify:"
    echo "  1. Connect GitHub repo at https://app.netlify.com"
    echo "  2. Netlify auto-detects netlify.toml"
    echo "  3. Set VITE_API_URL to your backend URL in site settings"
    ;;
  14)
    echo "Deploy frontend to Vercel:"
    echo "  1. Install Vercel CLI: npm i -g vercel"
    echo "  2. vercel --prod"
    echo "  3. Set VITE_API_URL environment variable in Vercel dashboard"
    ;;
  *)
    echo "Invalid choice."
    exit 1
    ;;
esac
