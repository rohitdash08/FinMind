#!/bin/bash
set -euo pipefail

# FinMind — AWS ECS Fargate Deployment Script
# ────────────────────────────────────────────
# Prerequisites: AWS CLI configured, Docker installed
# Usage: ./deploy/aws/deploy.sh

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || { echo "❌ AWS CLI not configured. Run 'aws configure' first."; exit 1; })
STACK_NAME="${STACK_NAME:-finmind}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"

echo "╔══════════════════════════════════════════╗"
echo "║  FinMind — AWS ECS Fargate Deployment    ║"
echo "╚══════════════════════════════════════════╝"
echo "  Region:  $REGION"
echo "  Account: $ACCOUNT_ID"
echo ""

# ── 1. Create ECR Repositories ────────────────────
echo "📦 Creating ECR repositories..."
for repo in finmind-api finmind-web; do
  aws ecr describe-repositories --repository-names "$repo" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$repo" --region "$REGION" --image-scanning-configuration scanOnPush=true
done

# ── 2. Login to ECR ───────────────────────────────
echo "🔑 Logging into ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# ── 3. Build and Push Images ──────────────────────
BACKEND_IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-api:latest"
FRONTEND_IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-web:latest"

echo "🔨 Building backend image..."
docker build -t finmind-api -f packages/backend/Dockerfile packages/backend/
docker tag finmind-api:latest "$BACKEND_IMAGE"
docker push "$BACKEND_IMAGE"

echo "🔨 Building frontend image..."
docker build -t finmind-web -f app/Dockerfile app/
docker tag finmind-web:latest "$FRONTEND_IMAGE"
docker push "$FRONTEND_IMAGE"

# ── 4. Get VPC and Subnets ────────────────────────
if [ -z "${VPC_ID:-}" ]; then
  echo "🔍 Auto-detecting default VPC..."
  VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region "$REGION")
  if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    echo "❌ No default VPC found. Set VPC_ID environment variable."
    exit 1
  fi
fi

if [ -z "${SUBNET_IDS:-}" ]; then
  echo "🔍 Auto-detecting subnets..."
  SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text --region "$REGION" | tr '\t' ',')
  # Take first 2 subnets
  SUBNET_IDS=$(echo "$SUBNET_IDS" | cut -d',' -f1-2)
fi

echo "  VPC:     $VPC_ID"
echo "  Subnets: $SUBNET_IDS"

# ── 5. Deploy CloudFormation ──────────────────────
echo "☁️  Deploying CloudFormation stack '$STACK_NAME'..."
aws cloudformation deploy \
  --template-file deploy/aws/cloudformation.yaml \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNET_IDS" \
    BackendImage="$BACKEND_IMAGE" \
    FrontendImage="$FRONTEND_IMAGE" \
    JwtSecret="$DB_PASSWORD" \
    DBPassword="$JWT_SECRET" \
  --capabilities CAPABILITY_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

# ── 6. Get Outputs ────────────────────────────────
ALB_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ALBURL`].OutputValue' \
  --output text --region "$REGION")

DB_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`DatabaseEndpoint`].OutputValue' \
  --output text --region "$REGION")

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ FinMind deployed successfully!       ║"
echo "╠══════════════════════════════════════════╣"
echo "║  URL:      $ALB_URL"
echo "║  Health:   $ALB_URL/health"
echo "║  Database: $DB_ENDPOINT"
echo "╠══════════════════════════════════════════╣"
echo "║  ⚠️  Save these credentials:             ║"
echo "║  DB Password: $DB_PASSWORD"
echo "║  JWT Secret:  $JWT_SECRET"
echo "╚══════════════════════════════════════════╝"
