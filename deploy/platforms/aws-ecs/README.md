# Deploy FinMind to AWS ECS Fargate

## Prerequisites
- AWS CLI configured with appropriate permissions
- VPC with public subnets
- RDS PostgreSQL instance
- ElastiCache Redis instance
- Secrets stored in AWS Secrets Manager

## Deploy
```bash
# Set up secrets
aws secretsmanager create-secret --name finmind/database-url --secret-string "postgresql+psycopg2://..."
aws secretsmanager create-secret --name finmind/redis-url --secret-string "redis://..."
aws secretsmanager create-secret --name finmind/jwt-secret --secret-string "$(openssl rand -hex 32)"

# Deploy
bash deploy/platforms/aws-ecs/deploy.sh
```

## Architecture
- ECS Fargate for serverless container execution
- ALB for load balancing and TLS termination
- RDS PostgreSQL for database
- ElastiCache Redis for caching
- CloudWatch for logging
