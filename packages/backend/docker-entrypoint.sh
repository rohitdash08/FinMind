#!/usr/bin/env sh
set -eu

if [ "${FINMIND_RUN_INIT_DB_ON_BOOT:-0}" = "1" ]; then
  python -m flask --app wsgi:app init-db
fi

export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_multiproc}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app
