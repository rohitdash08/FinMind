#!/bin/bash
set -euo pipefail

# FinMind - AWS ECS Fargate Deployment Script
# Prerequisites: AWS CLI configured, Docker installed

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
STACK_NAME="finmind"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"

echo "🚀 Deploying FinMind to AWS ECS Fargate..."
echo "   Region: $REGION | Account: $ACCOUNT_ID"

# Create ECR repositories
echo "📦 Creating ECR repositories..."
for repo in finmind-api finmind-web; do
  aws ecr describe-repositories --repository-names "$repo" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$repo" --region "$REGION"
done

# Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Build and push images
echo "🔨 Building and pushing backend..."
docker build -t finmind-api -f packages/backend/Dockerfile .
docker tag finmind-api:latest "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-api:latest"
docker push "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-api:latest"

echo "🔨 Building and pushing frontend..."
docker build -t finmind-web -f app/Dockerfile app/
docker tag finmind-web:latest "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-web:latest"
docker push "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-web:latest"

# Deploy CloudFormation
echo "☁️  Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file deploy/aws/ecs-fargate/cloudformation.yaml \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    DBPassword="$DB_PASSWORD" \
    JWTSecret="$JWT_SECRET" \
    BackendImage="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-api:latest" \
    FrontendImage="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/finmind-web:latest" \
  --capabilities CAPABILITY_IAM \
  --region "$REGION"

# Get outputs
ALB_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].Outputs[?OutputKey==`ALBURL`].OutputValue' --output text --region "$REGION")

echo ""
echo "🎉 FinMind deployed successfully!"
echo "   URL:    $ALB_URL"
echo "   Health: $ALB_URL/health"
echo ""
echo "   DB Password: $DB_PASSWORD (save this!)"
