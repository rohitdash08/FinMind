#!/usr/bin/env sh
set -eu

AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
AZURE_CONTAINER_APP_NAME="${AZURE_CONTAINER_APP_NAME:-finmind}"
APP_IMAGE="${APP_IMAGE:-}"
JWT_SECRET="${JWT_SECRET:-}"
DATABASE_URL="${DATABASE_URL:-}"
REDIS_URL="${REDIS_URL:-}"

if [ -z "$AZURE_RESOURCE_GROUP" ] || [ -z "$APP_IMAGE" ]; then
  echo "Set AZURE_RESOURCE_GROUP and APP_IMAGE before running deploy/azure/deploy.sh." >&2
  exit 1
fi

if [ -z "$JWT_SECRET" ] || [ -z "$DATABASE_URL" ] || [ -z "$REDIS_URL" ]; then
  echo "Set JWT_SECRET, DATABASE_URL, and REDIS_URL before running deploy/azure/deploy.sh." >&2
  exit 1
fi

docker manifest inspect "$APP_IMAGE" >/dev/null

az deployment group create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --template-file deploy/azure/containerapp.bicep \
  --parameters \
    containerAppName="$AZURE_CONTAINER_APP_NAME" \
    appImage="$APP_IMAGE" \
    jwtSecret="$JWT_SECRET" \
    databaseUrl="$DATABASE_URL" \
    redisUrl="$REDIS_URL" >/dev/null

APP_FQDN="$(az containerapp show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_CONTAINER_APP_NAME" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"

APP_URL="https://${APP_FQDN}"

printf '%s\n' "Azure Container Apps URL: $APP_URL"

./deploy/azure/validate.sh \
  --frontend-url "$APP_URL" \
  --api-url "$APP_URL"
