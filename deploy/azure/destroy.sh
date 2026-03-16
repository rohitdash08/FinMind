#!/usr/bin/env sh
set -eu

AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
AZURE_CONTAINER_APP_NAME="${AZURE_CONTAINER_APP_NAME:-finmind}"

if [ -z "$AZURE_RESOURCE_GROUP" ]; then
  echo "Set AZURE_RESOURCE_GROUP before running deploy/azure/destroy.sh." >&2
  exit 1
fi

az containerapp delete \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_CONTAINER_APP_NAME" \
  --yes
