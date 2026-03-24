#!/bin/bash
# FinMind - AWS ECS Fargate Deployment
set -euo pipefail
REGION=${AWS_REGION:-us-east-1}
CLUSTER="finmind-cluster"
echo "☁️ Deploying FinMind to AWS ECS Fargate..."
aws ecs create-cluster --cluster-name $CLUSTER --region $REGION
aws ecr create-repository --repository-name finmind/backend --region $REGION 2>/dev/null || true
aws ecr create-repository --repository-name finmind/frontend --region $REGION 2>/dev/null || true
ECR_URI=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$REGION.amazonaws.com
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI
docker build -f deploy/docker/Dockerfile.backend -t $ECR_URI/finmind/backend:latest ../..
docker build -f deploy/docker/Dockerfile.frontend -t $ECR_URI/finmind/frontend:latest ../..
docker push $ECR_URI/finmind/backend:latest
docker push $ECR_URI/finmind/frontend:latest
echo "✅ Images pushed! Create ECS service via AWS Console or use the task definition in deploy/kubernetes/"
