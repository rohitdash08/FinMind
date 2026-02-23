# Deploy FinMind on AWS App Runner

Simpler alternative to ECS Fargate — no VPC/ALB management needed.

## Prerequisites
- RDS PostgreSQL instance (or use `docker compose` PostgreSQL)
- ElastiCache Redis (or use Upstash/Redis Cloud)

## Deploy Backend

```bash
# Build and push to ECR first (see ecs-fargate/deploy.sh)

# Create App Runner service
aws apprunner create-service \
  --service-name finmind-api \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/finmind-api:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {
          "DATABASE_URL": "postgresql+psycopg2://user:pass@host:5432/finmind",
          "REDIS_URL": "redis://host:6379/0",
          "JWT_SECRET": "your-secret",
          "LOG_LEVEL": "INFO"
        }
      }
    },
    "AutoDeploymentsEnabled": true
  }' \
  --instance-configuration '{
    "Cpu": "0.25 vCPU",
    "Memory": "0.5 GB"
  }' \
  --health-check-configuration '{
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 10,
    "Timeout": 5
  }'
```

## Deploy Frontend

Host on S3 + CloudFront or use Vercel/Netlify (see respective guides).

## Cost

~$10-15/month for App Runner (pay per request when idle)
