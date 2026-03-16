#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${FINMIND_COMPOSE_FILE:-docker-compose.prod.yml}"
OUTPUT_FILE="${1:-docs/demo/finmind-deploy-demo.mp4}"
WORK_DIR="${2:-tmp/demo_recording}"
PLAYWRIGHT_IMAGE="${PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.55.0-noble}"
DEMO_API_URL="${FINMIND_DEMO_API_URL:-http://backend:8000}"
FRONTEND_ENV_PATH="/usr/share/nginx/html/env.js"
FRONTEND_ENV_BACKUP="/tmp/finmind-demo-env.js.bak"
EXPORT_SCREENSHOTS="${FINMIND_EXPORT_SCREENSHOTS:-0}"
DEMO_STAMP="${FINMIND_DEMO_STAMP:-$(date +%Y%m%d)}"
DEMO_SHA="${FINMIND_DEMO_SHA:-$(git rev-parse --short HEAD)}"
SCREENSHOT_WORK_DIR="$WORK_DIR/screenshots"

mkdir -p "$WORK_DIR"
RAW_VIDEO="$WORK_DIR/finmind-browser-demo.webm"

docker compose -f "$COMPOSE_FILE" up -d --build backend frontend >/dev/null

NETWORK_NAME="$(
  docker inspect "$(docker compose -f "$COMPOSE_FILE" ps -q frontend)" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    | head -n 1
)"

if [ -z "$NETWORK_NAME" ]; then
  echo "Could not determine the Compose network for the frontend service." >&2
  exit 1
fi

restore_frontend_env() {
  docker compose -f "$COMPOSE_FILE" exec -T frontend sh -lc "
    if [ -f '$FRONTEND_ENV_BACKUP' ]; then
      cp '$FRONTEND_ENV_BACKUP' '$FRONTEND_ENV_PATH'
      rm -f '$FRONTEND_ENV_BACKUP'
    fi
  " >/dev/null 2>&1 || true
}

trap restore_frontend_env EXIT HUP INT TERM

docker compose -f "$COMPOSE_FILE" exec -T frontend sh -lc "
  cp '$FRONTEND_ENV_PATH' '$FRONTEND_ENV_BACKUP'
  cat > '$FRONTEND_ENV_PATH' <<'EOF'
window.__FINMIND_API_URL__ = \"${DEMO_API_URL}\";
EOF
" >/dev/null

docker run --rm \
  --ipc=host \
  --network "$NETWORK_NAME" \
  -v "$PWD":/work \
  -w /work \
  "$PLAYWRIGHT_IMAGE" \
  sh -lc '
    mkdir -p /tmp/finmind-playwright &&
    cd /tmp/finmind-playwright &&
    npm init -y >/dev/null 2>&1 &&
    npm install --silent playwright@1.55.0 >/dev/null 2>&1 &&
    cp /work/scripts/validate-ui.mjs ./validate-ui.mjs &&
    node ./validate-ui.mjs \
      --base-url http://frontend \
      --health-url http://backend:8000/health/ready \
      --provider-name "local compose review" \
      --record-video "/work/'"$RAW_VIDEO"'" \
      --screenshot-dir "/work/'"$SCREENSHOT_WORK_DIR"'"
  '

ffmpeg -y \
  -i "$RAW_VIDEO" \
  -vf "scale=1280:-2,fps=30" \
  -c:v libx264 \
  -preset slow \
  -crf 26 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUTPUT_FILE" >/dev/null 2>&1

printf '%s\n' "Recorded dynamic demo video: $OUTPUT_FILE"

if [ "$EXPORT_SCREENSHOTS" = "1" ]; then
  for name in readiness signup bills expenses analytics; do
    cp \
      "$SCREENSHOT_WORK_DIR/${name}.png" \
      "docs/demo/${DEMO_STAMP}-${DEMO_SHA}-${name}.png"
  done
  printf '%s\n' "Exported screenshots: docs/demo/${DEMO_STAMP}-${DEMO_SHA}-{readiness,signup,bills,expenses,analytics}.png"
fi
