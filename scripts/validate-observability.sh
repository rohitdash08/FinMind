#!/usr/bin/env sh
set -eu

PROMETHEUS_URL="${FINMIND_PROMETHEUS_URL:-http://127.0.0.1:9090}"
GRAFANA_URL="${FINMIND_GRAFANA_URL:-http://127.0.0.1:3000}"

python3 - "$PROMETHEUS_URL" "$GRAFANA_URL" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

prometheus_url = sys.argv[1].rstrip("/")
grafana_url = sys.argv[2].rstrip("/")
required_jobs = {"backend", "postgres", "redis", "nginx"}

def fetch_json(url: str, timeout: int = 10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))

def fetch_text(url: str, timeout: int = 10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")

def wait_for(check, timeout: int = 120, interval: int = 3):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            result = check()
            if result:
                return result
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    if last_error:
        raise last_error
    raise RuntimeError("Timed out waiting for observability stack")

wait_for(lambda: fetch_text(f"{prometheus_url}/-/ready")[0] == 200)
status, grafana = wait_for(lambda: fetch_json(f"{grafana_url}/api/health"))
if status != 200 or grafana.get("database") != "ok":
    raise RuntimeError(f"Grafana health invalid: {grafana}")

_, targets_payload = wait_for(lambda: fetch_json(f"{prometheus_url}/api/v1/targets"))
active_targets = targets_payload.get("data", {}).get("activeTargets", [])
healthy_jobs = {
    target.get("labels", {}).get("job")
    for target in active_targets
    if target.get("health") == "up"
}
missing = sorted(required_jobs - healthy_jobs)
if missing:
    raise RuntimeError(f"Prometheus targets not healthy: {', '.join(missing)}")

print("FinMind observability smoke check passed")
PY
