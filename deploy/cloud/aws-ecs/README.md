# AWS ECS Fargate Deployment Guide
#
# This CloudFormation template deploys FinMind on ECS Fargate with:
# - Application Load Balancer (path-based routing)
# - Backend and Frontend as separate ECS services
# - Auto-scaling (CPU-based, 2-10 tasks)
# - CloudWatch Logs
# - Container Insights
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - A VPC with at least 2 public subnets
#   - Container images pushed to ECR or GHCR
#   - SSM Parameter Store values created:
#       /finmind/DATABASE_URL
#       /finmind/REDIS_URL
#       /finmind/JWT_SECRET
#
# Quick Start:
#
#   1. Store secrets in SSM Parameter Store:
#        aws ssm put-parameter --name /finmind/DATABASE_URL --type SecureString \
#          --value "postgresql+psycopg2://user:pass@host:5432/finmind"
#        aws ssm put-parameter --name /finmind/REDIS_URL --type SecureString \
#          --value "redis://host:6379/0"
#        aws ssm put-parameter --name /finmind/JWT_SECRET --type SecureString \
#          --value "$(openssl rand -hex 32)"
#
#   2. Deploy the stack:
#        aws cloudformation deploy \
#          --template-file deploy/cloud/aws-ecs/cloudformation.json \
#          --stack-name finmind \
#          --capabilities CAPABILITY_IAM \
#          --parameter-overrides \
#            VpcId=vpc-xxx \
#            SubnetIds=subnet-aaa,subnet-bbb \
#            DbPassword=your-secure-password
#
#   3. Get the ALB URL:
#        aws cloudformation describe-stacks --stack-name finmind \
#          --query 'Stacks[0].Outputs[?OutputKey==`ALBDnsName`].OutputValue' \
#          --output text
#
# Database Options:
#   - Amazon RDS PostgreSQL (recommended for production)
#   - Amazon ElastiCache for Redis
#   - Create these separately and pass connection strings via SSM
#
# Cost Optimization:
#   - Use Fargate Spot for non-critical workloads
#   - Scale down to 1 task during off-hours
#   - Use free-tier eligible RDS and ElastiCache instances
