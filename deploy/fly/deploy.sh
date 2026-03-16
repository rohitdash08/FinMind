#!/usr/bin/env sh
set -eu

APP_PREFIX="${APP_PREFIX:-finmind}"
BACKEND_APP="${BACKEND_APP:-${APP_PREFIX}-backend}"
FRONTEND_APP="${FRONTEND_APP:-${APP_PREFIX}-frontend}"
REGION="${FLY_REGION:-sjc}"
BACKEND_URL="${BACKEND_URL:-https://${BACKEND_APP}.fly.dev}"
BACKEND_TMP="$(mktemp)"
FRONTEND_TMP="$(mktemp)"

cleanup() {
  rm -f "$BACKEND_TMP" "$FRONTEND_TMP"
}

trap cleanup EXIT INT TERM

sed \
  -e "s/__BACKEND_APP__/${BACKEND_APP}/g" \
  -e "s/primary_region = \"sjc\"/primary_region = \"${REGION}\"/" \
  deploy/fly/fly.backend.toml > "$BACKEND_TMP"

sed \
  -e "s/__FRONTEND_APP__/${FRONTEND_APP}/g" \
  -e "s#__BACKEND_URL__#${BACKEND_URL}#g" \
  -e "s/primary_region = \"sjc\"/primary_region = \"${REGION}\"/" \
  deploy/fly/fly.frontend.toml > "$FRONTEND_TMP"

flyctl apps create "$BACKEND_APP" >/dev/null 2>&1 || true
flyctl apps create "$FRONTEND_APP" >/dev/null 2>&1 || true

if [ -n "${DATABASE_URL:-}" ] || [ -n "${REDIS_URL:-}" ] || [ -n "${JWT_SECRET:-}" ]; then
  flyctl secrets set \
    ${DATABASE_URL:+DATABASE_URL="$DATABASE_URL"} \
    ${REDIS_URL:+REDIS_URL="$REDIS_URL"} \
    ${JWT_SECRET:+JWT_SECRET="$JWT_SECRET"} \
    --app "$BACKEND_APP"
fi

flyctl deploy --config "$BACKEND_TMP" --remote-only
flyctl deploy --config "$FRONTEND_TMP" --remote-only
