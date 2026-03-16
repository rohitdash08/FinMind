#!/usr/bin/env sh
set -eu

OUTPUT_FILE="${1:-docs/demo/render-one-click-deploy-proof.mp4}"
WORK_DIR="${2:-tmp/render_proof_video}"
PLAYWRIGHT_TMP_DIR="${FINMIND_PLAYWRIGHT_TMP_DIR:-/tmp/finmind-playwright-local}"
REPO_ROOT="$(CDPATH='' cd "$(dirname "$0")/.." && pwd)"
WORK_DIR_ABS="$REPO_ROOT/$WORK_DIR"
OUTPUT_FILE_ABS="$REPO_ROOT/$OUTPUT_FILE"
RAW_VIDEO="$WORK_DIR_ABS/render-proof.webm"
RENDER_PROFILE_DIR="${FINMIND_RENDER_PROFILE_DIR:-$WORK_DIR_ABS/chrome-profile}"
DEPLOY_URL="${FINMIND_RENDER_DEPLOY_URL:-https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fjuzigu40-ui%2FFinMind%2Ftree%2Fcodex%2Ffinmind-144-deploy-bounty}"
BACKEND_DASHBOARD_URL="${FINMIND_RENDER_BACKEND_DASHBOARD_URL:-https://dashboard.render.com/web/srv-d6rgj19aae7s73d97rfg}"
FRONTEND_URL="${FINMIND_RENDER_FRONTEND_URL:-https://finmind-frontend-sexs.onrender.com}"
HEALTH_URL="${FINMIND_RENDER_HEALTH_URL:-https://finmind-backend-ht43.onrender.com/health/ready}"
COMMIT_SHA="${FINMIND_RENDER_PROOF_SHA:-63ab7de}"

mkdir -p "$WORK_DIR_ABS"
mkdir -p "$PLAYWRIGHT_TMP_DIR"
mkdir -p "$RENDER_PROFILE_DIR"

if [ ! -d "$PLAYWRIGHT_TMP_DIR/node_modules/playwright" ]; then
  (
    cd "$PLAYWRIGHT_TMP_DIR"
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm init -y >/dev/null 2>&1
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --silent playwright@1.55.0 >/dev/null 2>&1
  )
fi

cp "$REPO_ROOT/scripts/record-render-proof-video.mjs" "$PLAYWRIGHT_TMP_DIR/record-render-proof-video.mjs"

(
  cd "$PLAYWRIGHT_TMP_DIR"
  node ./record-render-proof-video.mjs \
    --output "$RAW_VIDEO" \
    --user-data-dir "$RENDER_PROFILE_DIR" \
    --deploy-url "$DEPLOY_URL" \
    --backend-dashboard-url "$BACKEND_DASHBOARD_URL" \
    --frontend-url "$FRONTEND_URL" \
    --health-url "$HEALTH_URL" \
    --commit-sha "$COMMIT_SHA"
)

ffmpeg -y \
  -i "$RAW_VIDEO" \
  -vf "scale=1280:-2,fps=30" \
  -c:v libx264 \
  -preset slow \
  -crf 26 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUTPUT_FILE_ABS" >/dev/null 2>&1

printf '%s\n' "Recorded Render proof video: $OUTPUT_FILE_ABS"
