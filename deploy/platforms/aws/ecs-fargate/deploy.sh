#!/usr/bin/env bash
# FinMind - AWS ECS Fargate Deployment
# Prerequisites: AWS CLI configured, ECR repository created
set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID}"
CLUSTER_NAME="${CLUSTER_NAME:-finmind-cluster}"
SERVICE_NAME="${SERVICE_NAME:-finmind-backend}"
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "=== FinMind ECS Fargate Deployment ==="

# Step 1: Authenticate with ECR
echo "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO"

# Step 2: Build and push backend image
echo "Building backend image..."
docker build -t finmind-backend ./packages/backend
docker tag finmind-backend:latest "$ECR_REPO/finmind-backend:latest"
docker push "$ECR_REPO/finmind-backend:latest"

# Step 3: Build and push frontend image
echo "Building frontend image..."
docker build -t finmind-frontend ./app
docker tag finmind-frontend:latest "$ECR_REPO/finmind-frontend:latest"
docker push "$ECR_REPO/finmind-frontend:latest"

# Step 4: Store secrets in SSM Parameter Store
echo "Checking SSM parameters..."
for param in DATABASE_URL REDIS_URL JWT_SECRET GEMINI_API_KEY; do
    if ! aws ssm get-parameter --name "/finmind/$param" --region "$AWS_REGION" &>/dev/null; then
        echo "WARNING: SSM parameter /finmind/$param not found. Create it with:"
        echo "  aws ssm put-parameter --name '/finmind/$param' --type SecureString --value 'YOUR_VALUE'"
    fi
done

# Step 5: Register task definition
echo "Registering task definition..."
TASK_DEF=$(envsubst < deploy/platforms/aws/ecs-fargate/task-definition.json)
aws ecs register-task-definition --cli-input-json "$TASK_DEF" --region "$AWS_REGION"

# Step 6: Create or update the service
if aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$SERVICE_NAME" --region "$AWS_REGION" | grep -q "ACTIVE"; then
    echo "Updating existing service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --task-definition finmind \
        --force-new-deployment \
        --region "$AWS_REGION"
else
    echo "Creating new service..."
    aws ecs create-service \
        --cluster "$CLUSTER_NAME" \
        --service-name "$SERVICE_NAME" \
        --task-definition finmind \
        --desired-count 2 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS}],securityGroups=[${SECURITY_GROUP_IDS}],assignPublicIp=ENABLED}" \
        --region "$AWS_REGION"
fi

echo "=== Deployment complete! ==="
echo "Check status: aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME"
