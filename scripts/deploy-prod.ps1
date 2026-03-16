Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path .env)) {
  throw ".env not found. Copy .env.example to .env and fill the required secrets first."
}

if ($env:FINMIND_COMPOSE_PROFILES) {
  $env:COMPOSE_PROFILES = $env:FINMIND_COMPOSE_PROFILES
} elseif ($env:COMPOSE_PROFILES) {
  $env:COMPOSE_PROFILES = $env:COMPOSE_PROFILES
}

docker compose -f docker-compose.prod.yml up -d --build
