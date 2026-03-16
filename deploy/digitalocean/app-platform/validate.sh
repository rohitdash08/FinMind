#!/usr/bin/env sh
set -eu

FRONTEND_URL="${FRONTEND_URL:-}"
API_URL="${API_URL:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --frontend-url)
      FRONTEND_URL="$2"
      shift 2
      ;;
    --api-url)
      API_URL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$FRONTEND_URL" ] || [ -z "$API_URL" ]; then
  echo "Usage: ./deploy/digitalocean/app-platform/validate.sh --frontend-url <url> --api-url <url>" >&2
  exit 1
fi

./scripts/validate-public-deployment.sh \
  --provider-name "DigitalOcean App Platform" \
  --frontend-url "$FRONTEND_URL" \
  --api-base-url "$API_URL"
