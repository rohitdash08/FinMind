# AWS Deployment Guide

## Option A: ECS Fargate (CloudFormation)

### Prerequisites
- AWS CLI configured with credentials
- A VPC with public subnets
- ECR repositories for backend and frontend images
- RDS PostgreSQL instance
- ElastiCache Redis instance

### Steps

1. **Build and push Docker images to ECR:**
   ```bash
   # Create ECR repos
   aws ecr create-repository --repository-name finmind-backend
   aws ecr create-repository --repository-name finmind-frontend

   # Login to ECR
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

   # Build and push
   docker build -t finmind-backend -f packages/backend/Dockerfile packages/backend
   docker tag finmind-backend:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
   docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

   docker build -t finmind-frontend -f app/Dockerfile app
   docker tag finmind-frontend:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-frontend:latest
   docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-frontend:latest
   ```

2. **Deploy the CloudFormation stack:**
   ```bash
   aws cloudformation deploy \
     --template-file deploy/aws/cloudformation.yaml \
     --stack-name finmind \
     --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides \
       VpcId=vpc-xxxxx \
       SubnetIds=subnet-aaa,subnet-bbb \
       BackendImage=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest \
       FrontendImage=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/finmind-frontend:latest \
       DatabaseUrl=postgresql+psycopg2://user:pass@rds-host:5432/finmind \
       RedisUrl=redis://elasticache-host:6379/0 \
       JwtSecret=$(openssl rand -hex 32)
   ```

3. **Verify:**
   ```bash
   aws ecs list-services --cluster finmind
   # Get task public IP and check /health
   ```

## Option B: App Runner

Simpler but less configurable. See `deploy/aws/apprunner.yaml` for the service config reference. Use the AWS Console or CLI:

```bash
aws apprunner create-service --cli-input-json file://deploy/aws/apprunner.json
```

**Note:** App Runner doesn't support multi-container. Deploy backend only; host frontend on S3+CloudFront or Amplify.

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
