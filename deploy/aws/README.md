# AWS Deployment

## ECS Fargate (Recommended)

### Prerequisites
```bash
# Install AWS CLI
aws configure
```

### 1. Create ECR Repository
```bash
aws ecr create-repository --repository-name finmind-backend
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

### 2. Build and Push Image
```bash
cd packages/backend
docker build -t finmind-backend .
docker tag finmind-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
```

### 3. Create RDS PostgreSQL
```bash
aws rds create-db-instance \
  --db-instance-identifier finmind-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username finmind \
  --master-user-password YOUR_PASSWORD \
  --allocated-storage 20
```

### 4. Create ElastiCache Redis
```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id finmind-redis \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --num-cache-nodes 1
```

### 5. Store Secrets in SSM
```bash
aws ssm put-parameter --name "/finmind/database-url" --value "postgresql://..." --type SecureString
aws ssm put-parameter --name "/finmind/redis-url" --value "redis://..." --type SecureString
aws ssm put-parameter --name "/finmind/jwt-secret" --value "$(openssl rand -hex 32)" --type SecureString
```

### 6. Create ECS Cluster and Service
```bash
aws ecs create-cluster --cluster-name finmind

# Update ACCOUNT_ID in ecs-task-definition.json
aws ecs register-task-definition --cli-input-json file://deploy/aws/ecs-task-definition.json

aws ecs create-service \
  --cluster finmind \
  --service-name finmind-backend \
  --task-definition finmind-backend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

## App Runner (Simpler)

```bash
aws apprunner create-service \
  --service-name finmind \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest",
      "ImageRepositoryType": "ECR"
    }
  }'
```

## Frontend (S3 + CloudFront)

```bash
cd app && npm run build
aws s3 sync dist/ s3://finmind-frontend/
aws cloudfront create-invalidation --distribution-id DIST_ID --paths "/*"
```

## Cost Estimate

- Fargate (0.25 vCPU, 0.5GB): ~$10/month
- RDS t3.micro: ~$15/month
- ElastiCache t3.micro: ~$12/month
- ALB: ~$16/month
