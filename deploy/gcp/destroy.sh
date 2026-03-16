#!/usr/bin/env sh
set -eu

GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
GCP_REGION="${GCP_REGION:-us-central1}"
GCP_SERVICE_NAME="${GCP_SERVICE_NAME:-finmind}"

if [ -z "$GCP_PROJECT_ID" ]; then
  echo "Set GCP_PROJECT_ID before running deploy/gcp/destroy.sh." >&2
  exit 1
fi

gcloud run services delete "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --quiet
