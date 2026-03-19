#!/usr/bin/env bash
# FinMind — One-click AWS ECS Fargate deployment
# Prerequisites: aws CLI v2, Docker, jq
# Usage: ./deploy.sh [--region us-east-1] [--cluster finmind] [--image-tag latest]
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER="${ECS_CLUSTER:-finmind}"
SERVICE_BACKEND="${ECS_SERVICE_BACKEND:-finmind-backend}"
SERVICE_FRONTEND="${ECS_SERVICE_FRONTEND:-finmind-frontend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKEND_IMAGE="ghcr.io/rohitdash08/finmind-backend:${IMAGE_TAG}"
FRONTEND_IMAGE="ghcr.io/rohitdash08/finmind-frontend:${IMAGE_TAG}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# 1. Register updated task definitions
log "Registering backend task definition..."
BACKEND_TASK=$(aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json \
  --region "$REGION" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)
log "Backend task: $BACKEND_TASK"

# 2. Update services
log "Updating ECS service: $SERVICE_BACKEND..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE_BACKEND" \
  --task-definition "$BACKEND_TASK" \
  --force-new-deployment \
  --region "$REGION" \
  --output text --query 'service.serviceArn' | xargs -I{} log "Service ARN: {}"

# 3. Wait for stability
log "Waiting for backend service to stabilize (up to 10 minutes)..."
aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE_BACKEND" \
  --region "$REGION"

log "Deployment complete."
log "Backend health: $(aws ecs describe-services --cluster $CLUSTER --services $SERVICE_BACKEND --region $REGION --query 'services[0].runningCount' --output text) tasks running"
