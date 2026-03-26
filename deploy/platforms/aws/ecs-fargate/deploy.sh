#!/usr/bin/env bash
# AWS ECS Fargate Deployment Script
# Prerequisites: aws CLI configured, ECR repository created
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${ECS_CLUSTER:-finmind-cluster}"
SERVICE_NAME="${ECS_SERVICE:-finmind-service}"
ECR_REPO="${ECR_REPOSITORY:-finmind-backend}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

echo "======================================"
echo "  FinMind — AWS ECS Fargate Deploy"
echo "======================================"

# 1. Authenticate to ECR
echo "[1/5] Authenticating with ECR..."
aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# 2. Build and push
echo "[2/5] Building backend image..."
docker build -t "$ECR_REPO" -f packages/backend/Dockerfile packages/backend/
docker tag "$ECR_REPO:latest" "$ECR_URI:latest"
docker tag "$ECR_REPO:latest" "$ECR_URI:$(git rev-parse --short HEAD)"

echo "[3/5] Pushing to ECR..."
docker push "$ECR_URI:latest"
docker push "$ECR_URI:$(git rev-parse --short HEAD)"

# 3. Store secrets in SSM Parameter Store (first-time only)
echo "[4/5] Checking SSM parameters..."
for param in DATABASE_URL REDIS_URL JWT_SECRET GEMINI_API_KEY; do
    if ! aws ssm get-parameter --name "/finmind/${param}" --region "$REGION" &>/dev/null; then
        echo "  WARNING: /finmind/${param} not found in SSM. Set it with:"
        echo "    aws ssm put-parameter --name '/finmind/${param}' --value 'YOUR_VALUE' --type SecureString --region $REGION"
    fi
done

# 4. Update task definition with correct ECR URI and deploy
echo "[5/5] Deploying to ECS..."
TASK_DEF=$(cat deploy/platforms/aws/ecs-fargate/task-definition.json | \
    sed "s|ghcr.io/rohitdash08/finmind-backend:latest|${ECR_URI}:latest|g" | \
    sed "s|arn:aws:ssm:us-east-1::|arn:aws:ssm:${REGION}:${ACCOUNT_ID}|g" | \
    sed "s|arn:aws:iam::|arn:aws:iam::${ACCOUNT_ID}|g")

TASK_ARN=$(echo "$TASK_DEF" | aws ecs register-task-definition \
    --cli-input-json "file:///dev/stdin" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text --region "$REGION")

aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --task-definition "$TASK_ARN" \
    --force-new-deployment \
    --region "$REGION" > /dev/null

echo ""
echo "Deployment initiated. Monitor with:"
echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION"
