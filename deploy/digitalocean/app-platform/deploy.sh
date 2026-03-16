#!/usr/bin/env sh
set -eu

SPEC_PATH="${SPEC_PATH:-deploy/digitalocean/app-platform/app.yaml}"
APP_ID="${APP_ID:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --spec)
      SPEC_PATH="$2"
      shift 2
      ;;
    --app-id)
      APP_ID="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$APP_ID" ]; then
  APP_JSON="$(doctl apps create --spec "$SPEC_PATH" --format ID --no-header --output json)"
  APP_ID="$(printf '%s' "$APP_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["ID"])')"
else
  doctl apps update "$APP_ID" --spec "$SPEC_PATH" >/dev/null
fi

APP_DETAILS="$(doctl apps get "$APP_ID" --output json)"

python3 - <<'PY' "$APP_DETAILS"
import json
import sys

raw = json.loads(sys.argv[1])
app = raw[0] if isinstance(raw, list) else raw
default_ingress = app.get("default_ingress") or app.get("live_url") or ""
print(f"DigitalOcean App Platform app id: {app.get('id') or app.get('ID')}")
if default_ingress:
    print(f"DigitalOcean App Platform URL: https://{default_ingress}" if not default_ingress.startswith("http") else f"DigitalOcean App Platform URL: {default_ingress}")
else:
    print("DigitalOcean App Platform URL: <pending DNS/ingress assignment>")
PY
