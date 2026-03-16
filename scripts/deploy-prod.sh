#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  echo ".env not found. Copy .env.example to .env and fill the required secrets first." >&2
  exit 1
fi

if [ -n "${FINMIND_COMPOSE_PROFILES:-${COMPOSE_PROFILES:-}}" ]; then
  export COMPOSE_PROFILES="${FINMIND_COMPOSE_PROFILES:-${COMPOSE_PROFILES:-}}"
fi

docker compose -f docker-compose.prod.yml up -d --build
