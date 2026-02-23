# Deploy FinMind on AWS ECS Fargate

## Quick Deploy

```bash
# Configure AWS CLI
aws configure

# Deploy everything (VPC, RDS, ElastiCache, ECS, ALB)
chmod +x deploy/aws/ecs-fargate/deploy.sh
./deploy/aws/ecs-fargate/deploy.sh
```

## Architecture

```
Internet → ALB → ECS Fargate (API + Frontend)
                    ↓
              RDS PostgreSQL + ElastiCache Redis
```

## What Gets Created

- VPC with public/private subnets
- Application Load Balancer
- ECS Fargate cluster with API and Frontend services
- RDS PostgreSQL 16 (db.t3.micro)
- ElastiCache Redis (cache.t3.micro)
- CloudWatch Log Groups
- Security groups with least-privilege rules

## Cleanup

```bash
aws cloudformation delete-stack --stack-name finmind
```

## Cost Estimate

~$40-60/month (Fargate + RDS + ElastiCache minimum tiers)
