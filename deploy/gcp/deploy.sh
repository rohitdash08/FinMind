#!/usr/bin/env sh
set -eu

GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
GCP_REGION="${GCP_REGION:-us-central1}"
GCP_SERVICE_NAME="${GCP_SERVICE_NAME:-finmind}"
GCP_ARTIFACT_REPOSITORY="${GCP_ARTIFACT_REPOSITORY:-finmind}"
APP_IMAGE="${APP_IMAGE:-}"
APP_IMAGE_TAG="${APP_IMAGE_TAG:-$(git rev-parse --short HEAD)}"
DATABASE_URL="${DATABASE_URL:-}"
REDIS_URL="${REDIS_URL:-}"
JWT_SECRET="${JWT_SECRET:-}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-1.5-flash}"
SKIP_BUILD="${SKIP_BUILD:-0}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-build)
      SKIP_BUILD="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$GCP_PROJECT_ID" ]; then
  echo "Set GCP_PROJECT_ID before running deploy/gcp/deploy.sh." >&2
  exit 1
fi

if [ -z "$DATABASE_URL" ] || [ -z "$REDIS_URL" ] || [ -z "$JWT_SECRET" ]; then
  echo "Set DATABASE_URL, REDIS_URL, and JWT_SECRET before running deploy/gcp/deploy.sh." >&2
  exit 1
fi

if [ -z "$APP_IMAGE" ]; then
  APP_IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GCP_ARTIFACT_REPOSITORY}/app:${APP_IMAGE_TAG}"
fi

if [ "$SKIP_BUILD" != "1" ]; then
  gcloud artifacts repositories describe "$GCP_ARTIFACT_REPOSITORY" \
    --project "$GCP_PROJECT_ID" \
    --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$GCP_ARTIFACT_REPOSITORY" \
    --project "$GCP_PROJECT_ID" \
    --location "$GCP_REGION" \
    --repository-format docker

  gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet
  docker build -f Dockerfile.fullstack -t "$APP_IMAGE" .
  docker push "$APP_IMAGE"
fi

ENV_FILE="$(mktemp)"
cleanup() {
  rm -f "$ENV_FILE"
}
trap cleanup EXIT INT TERM

python3 - <<'PY' "$ENV_FILE" "$DATABASE_URL" "$REDIS_URL" "$JWT_SECRET" "$LOG_LEVEL" "$GEMINI_MODEL"
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
values = {
    "DATABASE_URL": sys.argv[2],
    "REDIS_URL": sys.argv[3],
    "JWT_SECRET": sys.argv[4],
    "LOG_LEVEL": sys.argv[5],
    "GEMINI_MODEL": sys.argv[6],
    "FINMIND_SERVE_SPA": "1",
}
path.write_text("\n".join(f"{key}: {json.dumps(value)}" for key, value in values.items()) + "\n")
PY

gcloud run deploy "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8000 \
  --image "$APP_IMAGE" \
  --env-vars-file "$ENV_FILE"

APP_URL="$(gcloud run services describe "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --format 'value(status.url)')"

printf '%s\n' "GCP Cloud Run URL: $APP_URL"

./deploy/gcp/validate.sh \
  --frontend-url "$APP_URL" \
  --api-url "$APP_URL"
