# FinMind — AWS Deployment

## Option 1: ECS Fargate + RDS + ElastiCache (Full Stack)

One-command deployment using CloudFormation. Creates the entire infrastructure:
- ECS Fargate cluster with backend + frontend services
- RDS PostgreSQL 16 (encrypted, auto-backup)
- ElastiCache Redis 7
- Application Load Balancer with path-based routing
- Security groups, IAM roles, CloudWatch logs

### Prerequisites

- AWS CLI configured (`aws configure`)
- Docker installed
- A VPC with at least 2 subnets in different AZs

### Quick Deploy

```bash
# Run the deploy script (handles ECR, build, push, CloudFormation)
chmod +x deploy/aws/deploy.sh
./deploy/aws/deploy.sh
```

### Manual Deploy

```bash
# 1. Create ECR repositories
aws ecr create-repository --repository-name finmind-api
aws ecr create-repository --repository-name finmind-web

# 2. Login to ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

# 3. Build and push images
docker build -t ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-api:latest -f packages/backend/Dockerfile packages/backend/
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-api:latest

docker build -t ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-web:latest -f app/Dockerfile app/
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-web:latest

# 4. Deploy CloudFormation
aws cloudformation deploy \
  --template-file deploy/aws/cloudformation.yaml \
  --stack-name finmind \
  --parameter-overrides \
    VpcId=vpc-xxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    BackendImage=${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-api:latest \
    FrontendImage=${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/finmind-web:latest \
    JwtSecret=$(openssl rand -hex 32) \
    DBPassword=$(openssl rand -hex 16) \
  --capabilities CAPABILITY_IAM
```

### Outputs

```bash
aws cloudformation describe-stacks --stack-name finmind --query 'Stacks[0].Outputs'
```

### Cleanup

```bash
aws cloudformation delete-stack --stack-name finmind
```

---

## Option 2: App Runner (Backend Only)

Simpler option for the backend. Pair with Netlify/Vercel for frontend.

```bash
# Push image to ECR first (see above), then:
aws apprunner create-service --cli-input-yaml file://deploy/aws/apprunner.yaml
```

Config: `deploy/aws/apprunner.yaml`

---

## Files

| File | Description |
|------|-------------|
| `deploy.sh` | Automated deploy script (ECR + CloudFormation) |
| `cloudformation.yaml` | Full infrastructure template |
| `ecs-task-definition.json` | Standalone ECS task definition |
| `apprunner.yaml` | App Runner service config |

## Cost Estimate

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| ECS Fargate (2 tasks) | ~$30 |
| RDS db.t4g.micro | ~$15 |
| ElastiCache cache.t4g.micro | ~$12 |
| ALB | ~$16 |
| **Total** | **~$73/mo** |
