#!/usr/bin/env sh
set -eu

AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
AWS_STACK_NAME="${AWS_STACK_NAME:-finmind-ecs}"
ECR_REPOSITORY="${ECR_REPOSITORY:-finmind}"
APP_IMAGE_TAG="${APP_IMAGE_TAG:-$(git rev-parse --short HEAD)}"
DATABASE_URL="${DATABASE_URL:-}"
REDIS_URL="${REDIS_URL:-}"
JWT_SECRET="${JWT_SECRET:-}"
AWS_VPC_ID="${AWS_VPC_ID:-}"
AWS_PUBLIC_SUBNET_A="${AWS_PUBLIC_SUBNET_A:-}"
AWS_PUBLIC_SUBNET_B="${AWS_PUBLIC_SUBNET_B:-}"

if [ -z "$AWS_REGION" ] || [ -z "$AWS_ACCOUNT_ID" ]; then
  echo "Set AWS_REGION (or AWS_DEFAULT_REGION) and AWS_ACCOUNT_ID before running deploy/aws/deploy.sh." >&2
  exit 1
fi

if [ -z "$DATABASE_URL" ] || [ -z "$REDIS_URL" ] || [ -z "$JWT_SECRET" ]; then
  echo "Set DATABASE_URL, REDIS_URL, and JWT_SECRET before running deploy/aws/deploy.sh." >&2
  exit 1
fi

if [ -z "$AWS_VPC_ID" ] || [ -z "$AWS_PUBLIC_SUBNET_A" ] || [ -z "$AWS_PUBLIC_SUBNET_B" ]; then
  echo "Set AWS_VPC_ID, AWS_PUBLIC_SUBNET_A, and AWS_PUBLIC_SUBNET_B before running deploy/aws/deploy.sh." >&2
  exit 1
fi

APP_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${APP_IMAGE_TAG}"

aws ecr describe-repositories \
  --region "$AWS_REGION" \
  --repository-names "$ECR_REPOSITORY" >/dev/null 2>&1 || \
aws ecr create-repository \
  --region "$AWS_REGION" \
  --repository-name "$ECR_REPOSITORY" >/dev/null

aws ecr get-login-password --region "$AWS_REGION" | docker login \
  --username AWS \
  --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build -f Dockerfile.fullstack -t "$APP_IMAGE" .
docker push "$APP_IMAGE"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$AWS_STACK_NAME" \
  --template-file deploy/aws/cloudformation.yaml \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    VpcId="$AWS_VPC_ID" \
    PublicSubnetA="$AWS_PUBLIC_SUBNET_A" \
    PublicSubnetB="$AWS_PUBLIC_SUBNET_B" \
    ContainerImage="$APP_IMAGE" \
    DatabaseUrl="$DATABASE_URL" \
    RedisUrl="$REDIS_URL" \
    JwtSecret="$JWT_SECRET"

APP_URL="$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$AWS_STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='AppUrl'].OutputValue" \
  --output text)"

printf '%s\n' "AWS ECS Fargate URL: $APP_URL"

./deploy/aws/validate.sh \
  --frontend-url "$APP_URL" \
  --api-url "$APP_URL"
