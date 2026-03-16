#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${FINMIND_COMPOSE_FILE:-docker-compose.prod.yml}"
OUTPUT_DIR="${1:-output/review-artifacts}"

mkdir -p "$OUTPUT_DIR"

NETWORK_NAME="$(
  docker inspect "$(docker compose -f "$COMPOSE_FILE" --profile observability ps -q backend)" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    | head -n 1
)"

docker compose -f "$COMPOSE_FILE" --profile observability ps > "$OUTPUT_DIR/compose-ps.txt"

docker run --rm \
  --network "$NETWORK_NAME" \
  python:3.11-slim \
  python - <<'PY' > "$OUTPUT_DIR/review-checks.txt"
import urllib.request

checks = {
    "backend_health": "http://backend:8000/health",
    "backend_ready": "http://backend:8000/health/ready",
    "prometheus_ready": "http://prometheus:9090/-/ready",
    "grafana_health": "http://grafana:3000/api/health",
}

for name, url in checks.items():
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read().decode("utf-8")
    print(f"[{name}] {url}")
    print(body)
    print()
PY

docker run --rm \
  -v "$PWD":/work \
  -w /work \
  alpine/helm:3.16.2 \
  template finmind deploy/helm/finmind > "$OUTPUT_DIR/helm-render.yaml"

cat > "$OUTPUT_DIR/review-summary.md" <<EOF
# FinMind review artifact bundle

Generated from the production Compose + observability stack and the Helm chart render path.

Files:

- \`compose-ps.txt\`: service status snapshot
- \`review-checks.txt\`: backend, readiness, Prometheus, and Grafana responses
- \`helm-render.yaml\`: rendered Helm output used for review verification
EOF
