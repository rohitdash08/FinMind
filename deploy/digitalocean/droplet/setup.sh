#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/finmind}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
REPO_URL="${REPO_URL:-https://github.com/juzigu40-ui/FinMind.git}"
APP_GIT_REF="${APP_GIT_REF:-codex/finmind-144-deploy-bounty}"
APP_COMMIT_SHA="${APP_COMMIT_SHA:-}"
AUTO_START="${AUTO_START:-0}"
AUTO_VALIDATE="${AUTO_VALIDATE:-0}"
CHECKOUT_BRANCH="${CHECKOUT_BRANCH:-finmind-deploy}"

apt-get update
apt-get install -y docker.io docker-compose-plugin git
systemctl enable --now docker

if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git remote set-url origin "$REPO_URL"
git fetch --prune origin
git fetch --prune origin "$APP_GIT_REF"
git checkout -B "$CHECKOUT_BRANCH" FETCH_HEAD

if [ -n "$APP_COMMIT_SHA" ]; then
  git checkout --detach "$APP_COMMIT_SHA"
fi

CURRENT_SHA="$(git rev-parse --short HEAD)"
printf '%s\n' "FinMind droplet source:"
printf '  repo: %s\n' "$REPO_URL"
printf '  ref:  %s\n' "$APP_GIT_REF"
printf '  sha:  %s\n' "$CURRENT_SHA"

if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
  printf '%s\n' "Generated env file at $ENV_FILE. Fill secrets before the first production start."
else
  printf '%s\n' "Using existing env file at $ENV_FILE."
fi

if [ "$AUTO_VALIDATE" = "1" ] && [ "$AUTO_START" != "1" ]; then
  echo "AUTO_VALIDATE=1 requires AUTO_START=1 so the stack is running before validation." >&2
  exit 1
fi

if [ "$AUTO_START" = "1" ]; then
  docker compose -f docker-compose.prod.yml up -d --build
  printf '%s\n' "Production Compose stack started."
else
  printf '%s\n' "AUTO_START=0, so the stack was not started."
fi

if [ "$AUTO_VALIDATE" = "1" ]; then
  FINMIND_REVIEW_KEEP_RUNNING=1 ./scripts/review-deploy.sh
fi
