#!/usr/bin/env sh
set -eu

AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
AWS_STACK_NAME="${AWS_STACK_NAME:-finmind-ecs}"
ECR_REPOSITORY="${ECR_REPOSITORY:-finmind}"
DELETE_ECR_REPOSITORY="${DELETE_ECR_REPOSITORY:-0}"

if [ -z "$AWS_REGION" ]; then
  echo "Set AWS_REGION (or AWS_DEFAULT_REGION) before running deploy/aws/destroy.sh." >&2
  exit 1
fi

aws cloudformation delete-stack \
  --region "$AWS_REGION" \
  --stack-name "$AWS_STACK_NAME"

aws cloudformation wait stack-delete-complete \
  --region "$AWS_REGION" \
  --stack-name "$AWS_STACK_NAME"

if [ "$DELETE_ECR_REPOSITORY" = "1" ]; then
  aws ecr delete-repository \
    --region "$AWS_REGION" \
    --repository-name "$ECR_REPOSITORY" \
    --force
fi
