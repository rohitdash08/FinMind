#!/usr/bin/env sh
set -eu

COMPOSE_FILE="docker-compose.prod.yml"
KEEP_RUNNING="${FINMIND_REVIEW_KEEP_RUNNING:-0}"
CREATED_ENV=0

network_name() {
  docker inspect "$(docker compose -f "$COMPOSE_FILE" ps -q backend)" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    | head -n 1
}

cleanup() {
  if [ "$KEEP_RUNNING" != "1" ]; then
    docker compose -f "$COMPOSE_FILE" --profile observability down -v >/dev/null 2>&1 || true
  fi
  if [ "$CREATED_ENV" = "1" ]; then
    rm -f .env
  fi
}

trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  cp .env.example .env
  CREATED_ENV=1
fi

export COMPOSE_PROFILES=observability

docker compose -f "$COMPOSE_FILE" --profile observability up -d --build

NETWORK_NAME="$(network_name)"

docker run --rm \
  --network "$NETWORK_NAME" \
  -v "$PWD":/work \
  -w /work \
  python:3.11-slim \
  python scripts/smoke-deploy.py \
  --api-base-url http://backend:8000 \
  --frontend-url http://frontend:80

docker run --rm \
  --network "$NETWORK_NAME" \
  python:3.11-slim \
  python - <<'PY'
import json
import urllib.request


def check(url, *, contains=None):
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read().decode("utf-8")
    if contains and contains not in body:
        raise SystemExit(f"{url} did not contain {contains!r}")
    return body


check("http://prometheus:9090/-/ready", contains="Prometheus Server is Ready")
grafana = json.loads(check("http://grafana:3000/api/health"))
if grafana.get("database") != "ok":
    raise SystemExit(f"Grafana health was not ok: {grafana}")
PY

docker run --rm \
  -v "$PWD":/work \
  -w /work \
  alpine/helm:3.16.2 \
  lint deploy/helm/finmind

docker run --rm \
  -v "$PWD":/work \
  -w /work \
  alpine/helm:3.16.2 \
  template finmind deploy/helm/finmind > /tmp/finmind-helm-review.yaml

grep -q "kind: Ingress" /tmp/finmind-helm-review.yaml
grep -q "path: /health/ready" /tmp/finmind-helm-review.yaml
grep -q "name: finmind-prometheus" /tmp/finmind-helm-review.yaml
grep -q "name: finmind-grafana" /tmp/finmind-helm-review.yaml

printf '%s\n' "FinMind deployment review passed"
