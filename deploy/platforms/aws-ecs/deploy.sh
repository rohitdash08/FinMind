#!/bin/bash
set -euo pipefail

# FinMind - AWS ECS Fargate Deployment
# Prerequisites: AWS CLI configured, ECR repository created

REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="finmind-cluster"
SERVICE_NAME="finmind-service"
TASK_FAMILY="finmind"

echo "=== Deploying FinMind to AWS ECS Fargate ==="

# Create ECS cluster if not exists
aws ecs create-cluster --cluster-name "$CLUSTER_NAME" --region "$REGION" 2>/dev/null || true

# Register task definition
aws ecs register-task-definition \
    --cli-input-json file://deploy/platforms/aws-ecs/task-definition.json \
    --region "$REGION"

# Create or update service
if aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$SERVICE_NAME" --region "$REGION" | grep -q "ACTIVE"; then
    echo "Updating existing service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --task-definition "$TASK_FAMILY" \
        --force-new-deployment \
        --region "$REGION"
else
    echo "Creating new service..."
    aws ecs create-service \
        --cluster "$CLUSTER_NAME" \
        --service-name "$SERVICE_NAME" \
        --task-definition "$TASK_FAMILY" \
        --desired-count 2 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
        --region "$REGION"
fi

echo "Deployment initiated. Monitor at: https://$REGION.console.aws.amazon.com/ecs/"
