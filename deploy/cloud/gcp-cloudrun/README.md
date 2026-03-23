# GCP Cloud Run Deployment Guide
#
# Quick Start:
#   1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. Authenticate: gcloud auth login
#   3. Run the deploy script:
#        chmod +x deploy/cloud/gcp-cloudrun/deploy-cloudrun.sh
#        ./deploy/cloud/gcp-cloudrun/deploy-cloudrun.sh <PROJECT_ID> [REGION]
#
# What It Does:
#   - Enables required GCP APIs
#   - Builds Docker images via Cloud Build
#   - Creates secrets in Secret Manager
#   - Deploys backend and frontend as Cloud Run services
#   - Configures auto-scaling (0-10 instances)
#
# Database Setup:
#   - Create a Cloud SQL PostgreSQL instance:
#       gcloud sql instances create finmind-db \
#         --database-version=POSTGRES_16 --tier=db-f1-micro --region=us-central1
#   - Create a Memorystore Redis instance:
#       gcloud redis instances create finmind-redis \
#         --size=1 --region=us-central1
#   - Update the secrets with real connection strings
#
# Cost:
#   - Cloud Run scales to zero — you only pay for actual requests
#   - Cloud SQL and Memorystore have minimum costs
#   - Use free trial credits for initial testing
