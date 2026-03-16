#!/usr/bin/env sh
set -eu

API_BASE_URL="${FINMIND_API_BASE_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FINMIND_FRONTEND_URL:-http://127.0.0.1:8081}"

python3 scripts/smoke-deploy.py \
  --api-base-url "$API_BASE_URL" \
  --frontend-url "$FRONTEND_URL"
