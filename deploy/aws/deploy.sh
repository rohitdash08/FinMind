#!/usr/bin/env bash
set -euo pipefail

echo "=== FinMind AWS ECS Deploy ==="

REGION="${AWS_REGION:-us-east-1}"
CLUSTER="finmind"
SERVICE="finmind-backend"
TASK_FAMILY="finmind-backend"

aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$REGION.amazonaws.com"

docker tag finmind-backend:latest "$REPO_URI:latest"
docker push "$REPO_URI:latest"

TASK_DEF=$(aws ecs describe-task-definition --task-definition "$TASK_FAMILY" --region "$REGION")
NEW_TASK_DEF=$(echo "$TASK_DEF" | jq --arg IMG "$REPO_URI:latest" '.taskDefinition | .containerDefinitions[0].image = $IMG | {family, taskRoleArn, executionRoleArn, networkMode, containerDefinitions, volumes, placementConstraints, requiresCompatibilities, cpu, memory}' )

aws ecs register-task-definition --region "$REGION" --cli-input-json "$(echo "$NEW_TASK_DEF")" > /dev/null
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment --region "$REGION" > /dev/null

echo "Deployment triggered. Monitor at:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION"
