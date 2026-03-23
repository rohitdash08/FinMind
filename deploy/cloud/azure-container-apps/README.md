# Azure Container Apps Deployment Guide
#
# Quick Start:
#   1. Install Azure CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
#   2. Authenticate: az login
#   3. Run the deploy script:
#        chmod +x deploy/cloud/azure-container-apps/deploy-azure.sh
#        ./deploy/cloud/azure-container-apps/deploy-azure.sh [RESOURCE_GROUP] [LOCATION]
#
# What It Does:
#   - Creates a resource group and Container Apps environment
#   - Provisions Azure Database for PostgreSQL (Flexible Server)
#   - Provisions Azure Cache for Redis
#   - Deploys backend and frontend as Container Apps
#   - Configures auto-scaling (1-10 replicas)
#   - Sets up external ingress with HTTPS
#
# Manual Setup:
#   - You can also deploy via Azure Portal → Container Apps
#   - Or use Bicep/ARM templates for infrastructure-as-code
#
# Cost:
#   - Container Apps charges per vCPU-second and GiB-second
#   - PostgreSQL Burstable B1ms: ~$13/mo
#   - Redis Basic C0: ~$16/mo
#   - Total estimated: ~$35-50/mo for a basic deployment
