#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run backend tests." >&2
  exit 1
fi

ARGS="${*:-tests}"
echo "Running backend tests in Docker Compose..."
docker compose run --rm backend sh -lc "python -m pytest -q ${ARGS}"
