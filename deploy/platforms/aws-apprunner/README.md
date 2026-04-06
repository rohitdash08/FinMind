# Deploy FinMind to AWS App Runner

## Prerequisites
- AWS CLI configured
- RDS PostgreSQL + ElastiCache Redis (App Runner connects via VPC connector)

## Deploy
```bash
# Create App Runner service
aws apprunner create-service \
    --service-name finmind-backend \
    --source-configuration '{
        "CodeRepository": {
            "RepositoryUrl": "https://github.com/rohitdash08/FinMind",
            "SourceCodeVersion": {"Type": "BRANCH", "Value": "main"},
            "CodeConfiguration": {
                "ConfigurationSource": "REPOSITORY",
                "CodeConfigurationValues": {
                    "Runtime": "PYTHON_311",
                    "BuildCommand": "pip install -r packages/backend/requirements.txt",
                    "StartCommand": "cd packages/backend && gunicorn --bind 0.0.0.0:8000 wsgi:app",
                    "Port": "8000"
                }
            }
        },
        "AutoDeploymentsEnabled": true
    }' \
    --health-check-configuration "Path=/health,Protocol=HTTP,Interval=15,Timeout=10"
```
