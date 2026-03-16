#!/bin/sh
set -eu

cat >/usr/share/nginx/html/env.js <<EOF
window.__FINMIND_API_URL__ = "${FINMIND_API_URL:-}";
EOF
