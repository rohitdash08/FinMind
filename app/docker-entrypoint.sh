#!/bin/sh
set -e

# Determine the backend API URL for client-side JavaScript.
# Priority: BACKEND_URL > VITE_API_URL > empty (relative / same-origin)
API_URL="${BACKEND_URL:-${VITE_API_URL:-}}"

# Ensure URL has scheme if set
if [ -n "$API_URL" ]; then
  case "$API_URL" in
    http://*|https://*) ;;
    *) API_URL="https://${API_URL}" ;;
  esac
fi

# Inject runtime config — the frontend reads window.__FINMIND_API_URL__
CONFIG_FILE="/usr/share/nginx/html/runtime-config.js"
if [ -n "$API_URL" ]; then
  echo "window.__FINMIND_API_URL__ = \"${API_URL}\";" > "$CONFIG_FILE"
  echo "Runtime config: API_URL=${API_URL}"
else
  echo "// No API URL configured — using build-time VITE_API_URL or default" > "$CONFIG_FILE"
  echo "Warning: No BACKEND_URL or VITE_API_URL set."
fi

exec nginx -g 'daemon off;'
