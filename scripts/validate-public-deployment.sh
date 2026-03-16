#!/usr/bin/env sh
set -eu

FRONTEND_URL=""
API_BASE_URL=""
PROVIDER_NAME="public deployment"
COMMIT_SHA=""
SCREENSHOT_DIR=""
RECORD_VIDEO=""
PLAYWRIGHT_IMAGE="${FINMIND_PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.55.0-noble}"
REPO_ROOT="$(pwd)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --frontend-url)
      FRONTEND_URL="$2"
      shift 2
      ;;
    --api-base-url)
      API_BASE_URL="$2"
      shift 2
      ;;
    --provider-name)
      PROVIDER_NAME="$2"
      shift 2
      ;;
    --commit-sha)
      COMMIT_SHA="$2"
      shift 2
      ;;
    --screenshot-dir)
      SCREENSHOT_DIR="$2"
      shift 2
      ;;
    --record-video)
      RECORD_VIDEO="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$FRONTEND_URL" ] || [ -z "$API_BASE_URL" ]; then
  echo "Usage: ./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url> [--provider-name <label>] [--commit-sha <sha>] [--screenshot-dir <dir>] [--record-video <file>]" >&2
  exit 1
fi

printf '%s\n' "provider=$PROVIDER_NAME"
if [ -n "$COMMIT_SHA" ]; then
  printf '%s\n' "commit_sha=$COMMIT_SHA"
fi
printf '%s\n' "validated_at_utc=$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
printf '%s\n' "frontend_url=$FRONTEND_URL"
printf '%s\n' "api_url=$API_BASE_URL"
printf '%s\n' "health_url=${API_BASE_URL%/}/health/ready"

python3 scripts/smoke-deploy.py \
  --api-base-url "$API_BASE_URL" \
  --frontend-url "$FRONTEND_URL" \
  --provider-name "$PROVIDER_NAME" \
  --commit-sha "$COMMIT_SHA"

DOCKER_UI_CMD='
  mkdir -p /tmp/finmind-playwright &&
  cd /tmp/finmind-playwright &&
  npm init -y >/dev/null 2>&1 &&
  npm install --silent playwright@1.55.0 >/dev/null 2>&1 &&
  cp /work/scripts/validate-ui.mjs ./validate-ui.mjs &&
  node ./validate-ui.mjs \
    --base-url "$FINMIND_UI_BASE_URL" \
    --health-url "$FINMIND_UI_HEALTH_URL" \
    --provider-name "$FINMIND_UI_PROVIDER_NAME" \
    --commit-sha "$FINMIND_UI_COMMIT_SHA" \
    ${FINMIND_UI_SCREENSHOT_DIR:+--screenshot-dir "$FINMIND_UI_SCREENSHOT_DIR"} \
    ${FINMIND_UI_RECORD_VIDEO:+--record-video "$FINMIND_UI_RECORD_VIDEO"}
'

if docker run --rm \
  --ipc=host \
  -e FINMIND_UI_BASE_URL="$FRONTEND_URL" \
  -e FINMIND_UI_HEALTH_URL="${API_BASE_URL%/}/health/ready" \
  -e FINMIND_UI_PROVIDER_NAME="$PROVIDER_NAME" \
  -e FINMIND_UI_COMMIT_SHA="$COMMIT_SHA" \
  -e FINMIND_UI_SCREENSHOT_DIR="$SCREENSHOT_DIR" \
  -e FINMIND_UI_RECORD_VIDEO="$RECORD_VIDEO" \
  -v "$PWD":/work \
  -w /work \
  "$PLAYWRIGHT_IMAGE" \
  sh -lc "$DOCKER_UI_CMD"; then
  printf '%s\n' "ui_runner=docker"
else
  printf '%s\n' "ui_runner=local-chrome-fallback"
  PLAYWRIGHT_TMP_DIR="${FINMIND_PLAYWRIGHT_TMP_DIR:-/tmp/finmind-playwright-local}"
  mkdir -p "$PLAYWRIGHT_TMP_DIR"
  (
    cd "$PLAYWRIGHT_TMP_DIR"
    if [ ! -d node_modules/playwright ]; then
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm init -y >/dev/null 2>&1
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --silent playwright@1.55.0 >/dev/null 2>&1
    fi
    cp "$REPO_ROOT/scripts/validate-ui.mjs" ./validate-ui.mjs
    FINMIND_PLAYWRIGHT_CHANNEL=chrome node ./validate-ui.mjs \
      --base-url "$FRONTEND_URL" \
      --health-url "${API_BASE_URL%/}/health/ready" \
      --provider-name "$PROVIDER_NAME" \
      --commit-sha "$COMMIT_SHA" \
      ${SCREENSHOT_DIR:+--screenshot-dir "$SCREENSHOT_DIR"} \
      ${RECORD_VIDEO:+--record-video "$RECORD_VIDEO"}
  )
fi
