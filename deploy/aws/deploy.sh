#!/usr/bin/env bash
# ============================================================================
# FinMind — AWS ECS Fargate Deployment Script
# ============================================================================
# Deploys the FinMind backend (Python/Flask) and frontend (React/Vite/nginx)
# to AWS ECS Fargate with ECR, ALB, CloudWatch logging, and auto-scaling.
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate IAM permissions
#   - Docker installed and running
#   - jq installed
#
# Usage:
#   ./deploy.sh [--region us-east-1] [--env production]
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via environment variables or CLI flags
# ---------------------------------------------------------------------------
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"
PROJECT_NAME="finmind"
CLUSTER_NAME="${PROJECT_NAME}-cluster"
SERVICE_NAME="${PROJECT_NAME}-service"
BACKEND_REPO="${PROJECT_NAME}-backend"
FRONTEND_REPO="${PROJECT_NAME}-frontend"
BACKEND_DOCKERFILE="packages/backend/Dockerfile"
FRONTEND_DOCKERFILE="app/Dockerfile"
DESIRED_COUNT=2
CPU=512
MEMORY=1024

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region) AWS_REGION="$2"; shift 2 ;;
    --env)    ENVIRONMENT="$2"; shift 2 ;;
    *)        echo "Unknown option: $1"; exit 1 ;;
  esac
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== FinMind AWS ECS Fargate Deployment ==="
echo "Region:      ${AWS_REGION}"
echo "Account:     ${ACCOUNT_ID}"
echo "Environment: ${ENVIRONMENT}"
echo "Project Root: ${PROJECT_ROOT}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Authenticate Docker with ECR
# ---------------------------------------------------------------------------
echo ">>> Step 1: Authenticating Docker with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_BASE}"

# ---------------------------------------------------------------------------
# Step 2: Create ECR repositories (idempotent)
# ---------------------------------------------------------------------------
echo ">>> Step 2: Creating ECR repositories..."
for repo in "${BACKEND_REPO}" "${FRONTEND_REPO}"; do
  if ! aws ecr describe-repositories --repository-names "${repo}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    aws ecr create-repository \
      --repository-name "${repo}" \
      --region "${AWS_REGION}" \
      --image-scanning-configuration scanOnPush=true \
      --encryption-configuration encryptionType=AES256
    echo "  Created ECR repository: ${repo}"
  else
    echo "  ECR repository already exists: ${repo}"
  fi

  # Set lifecycle policy to keep only the last 10 images
  aws ecr put-lifecycle-policy \
    --repository-name "${repo}" \
    --region "${AWS_REGION}" \
    --lifecycle-policy-text '{
      "rules": [{
        "rulePriority": 1,
        "description": "Keep last 10 images",
        "selection": {
          "tagStatus": "any",
          "countType": "imageCountMoreThan",
          "countNumber": 10
        },
        "action": { "type": "expire" }
      }]
    }' >/dev/null
done

# ---------------------------------------------------------------------------
# Step 3: Build and push Docker images
# ---------------------------------------------------------------------------
echo ">>> Step 3: Building and pushing Docker images..."

IMAGE_TAG="${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

# Backend
echo "  Building backend image..."
docker build \
  -t "${ECR_BASE}/${BACKEND_REPO}:${IMAGE_TAG}" \
  -t "${ECR_BASE}/${BACKEND_REPO}:latest" \
  -f "${PROJECT_ROOT}/${BACKEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/packages/backend"

echo "  Pushing backend image..."
docker push "${ECR_BASE}/${BACKEND_REPO}:${IMAGE_TAG}"
docker push "${ECR_BASE}/${BACKEND_REPO}:latest"

# Frontend
echo "  Building frontend image..."
docker build \
  -t "${ECR_BASE}/${FRONTEND_REPO}:${IMAGE_TAG}" \
  -t "${ECR_BASE}/${FRONTEND_REPO}:latest" \
  -f "${PROJECT_ROOT}/${FRONTEND_DOCKERFILE}" \
  "${PROJECT_ROOT}/app"

echo "  Pushing frontend image..."
docker push "${ECR_BASE}/${FRONTEND_REPO}:${IMAGE_TAG}"
docker push "${ECR_BASE}/${FRONTEND_REPO}:latest"

# ---------------------------------------------------------------------------
# Step 4: Create CloudWatch log group
# ---------------------------------------------------------------------------
echo ">>> Step 4: Creating CloudWatch log group..."
aws logs create-log-group \
  --log-group-name "/ecs/${PROJECT_NAME}" \
  --region "${AWS_REGION}" 2>/dev/null || true

aws logs put-retention-policy \
  --log-group-name "/ecs/${PROJECT_NAME}" \
  --retention-in-days 30 \
  --region "${AWS_REGION}"

# ---------------------------------------------------------------------------
# Step 5: Create ECS cluster
# ---------------------------------------------------------------------------
echo ">>> Step 5: Creating ECS cluster..."
if ! aws ecs describe-clusters --clusters "${CLUSTER_NAME}" --region "${AWS_REGION}" \
    --query "clusters[?status=='ACTIVE'].clusterName" --output text | grep -q "${CLUSTER_NAME}"; then
  aws ecs create-cluster \
    --cluster-name "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    --capacity-providers FARGATE FARGATE_SPOT \
    --default-capacity-provider-strategy \
      capacityProvider=FARGATE,weight=1,base=1 \
      capacityProvider=FARGATE_SPOT,weight=3 \
    --setting name=containerInsights,value=enabled \
    --tags key=Project,value=FinMind key=Environment,value="${ENVIRONMENT}"
  echo "  Cluster created: ${CLUSTER_NAME}"
else
  echo "  Cluster already exists: ${CLUSTER_NAME}"
fi

# ---------------------------------------------------------------------------
# Step 6: Register task definition
# ---------------------------------------------------------------------------
echo ">>> Step 6: Registering ECS task definition..."

# Substitute placeholders in the task definition
TASK_DEF=$(cat "${SCRIPT_DIR}/ecs-task-definition.json" \
  | sed "s/ACCOUNT_ID/${ACCOUNT_ID}/g" \
  | sed "s/REGION/${AWS_REGION}/g")

TASK_DEF_ARN=$(echo "${TASK_DEF}" | aws ecs register-task-definition \
  --cli-input-json file:///dev/stdin \
  --region "${AWS_REGION}" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "  Registered task definition: ${TASK_DEF_ARN}"

# ---------------------------------------------------------------------------
# Step 7: Create or update ECS service
# ---------------------------------------------------------------------------
echo ">>> Step 7: Creating/updating ECS service..."

if aws ecs describe-services --cluster "${CLUSTER_NAME}" --services "${SERVICE_NAME}" \
    --region "${AWS_REGION}" --query "services[?status=='ACTIVE'].serviceName" \
    --output text 2>/dev/null | grep -q "${SERVICE_NAME}"; then

  # Update existing service with new task definition
  aws ecs update-service \
    --cluster "${CLUSTER_NAME}" \
    --service "${SERVICE_NAME}" \
    --task-definition "${TASK_DEF_ARN}" \
    --desired-count "${DESIRED_COUNT}" \
    --force-new-deployment \
    --region "${AWS_REGION}" >/dev/null

  echo "  Updated service: ${SERVICE_NAME}"
else
  # Create new service — requires VPC/subnet/SG/ALB setup done beforehand
  echo "  NOTE: Creating a new service requires networking resources."
  echo "  Ensure VPC, subnets, security groups, and ALB target groups exist."
  echo "  Update subnet/SG/TG ARNs in ecs-service.json before running."

  aws ecs create-service \
    --cluster "${CLUSTER_NAME}" \
    --service-name "${SERVICE_NAME}" \
    --task-definition "${TASK_DEF_ARN}" \
    --desired-count "${DESIRED_COUNT}" \
    --launch-type FARGATE \
    --platform-version LATEST \
    --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100" \
    --health-check-grace-period-seconds 120 \
    --region "${AWS_REGION}" \
    --network-configuration "$(jq -c '.networkConfiguration' "${SCRIPT_DIR}/ecs-service.json")" \
    --load-balancers "$(jq -c '.loadBalancers' "${SCRIPT_DIR}/ecs-service.json")" \
    --tags key=Project,value=FinMind key=Environment,value="${ENVIRONMENT}" >/dev/null

  echo "  Created service: ${SERVICE_NAME}"
fi

# ---------------------------------------------------------------------------
# Step 8: Configure auto-scaling
# ---------------------------------------------------------------------------
echo ">>> Step 8: Configuring auto-scaling..."

# Register the scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id "service/${CLUSTER_NAME}/${SERVICE_NAME}" \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10 \
  --region "${AWS_REGION}" 2>/dev/null || true

# CPU-based scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id "service/${CLUSTER_NAME}/${SERVICE_NAME}" \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name "${PROJECT_NAME}-cpu-scaling" \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }' \
  --region "${AWS_REGION}" >/dev/null

echo "  Auto-scaling configured (CPU target: 70%, min: 2, max: 10)"

# ---------------------------------------------------------------------------
# Step 9: Wait for deployment to stabilize
# ---------------------------------------------------------------------------
echo ">>> Step 9: Waiting for service to stabilize..."
aws ecs wait services-stable \
  --cluster "${CLUSTER_NAME}" \
  --services "${SERVICE_NAME}" \
  --region "${AWS_REGION}"

echo ""
echo "=== Deployment Complete ==="
echo "Image tag: ${IMAGE_TAG}"
echo "Cluster:   ${CLUSTER_NAME}"
echo "Service:   ${SERVICE_NAME}"
echo "Task def:  ${TASK_DEF_ARN}"
echo ""
echo "View logs:"
echo "  aws logs tail /ecs/${PROJECT_NAME} --follow --region ${AWS_REGION}"
echo ""
echo "View service status:"
echo "  aws ecs describe-services --cluster ${CLUSTER_NAME} --services ${SERVICE_NAME} --region ${AWS_REGION}"
