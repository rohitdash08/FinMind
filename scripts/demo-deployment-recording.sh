#!/usr/bin/env bash
# Demo script for FinMind Universal One-Click Deployment
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

EMAIL="demo-$(date +%s)@test.com"
PASSWORD='Demo1234!'

pause() {
  sleep "${1:-1}"
}

type_cmd() {
  echo ""
  echo -e "${CYAN}\$ ${BOLD}$1${NC}"
  pause 0.5
  eval "$1"
  pause 1
}

echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  FinMind — Universal One-Click Deployment Demo  ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
pause 1

# Show deploy configs
echo -e "${GREEN}▸ 1. Deployment configs for all platforms${NC}"
type_cmd "ls deploy/"
type_cmd "ls deploy/helm/finmind/"
type_cmd "ls deploy/aws/ deploy/gcp/ deploy/azure/ deploy/fly/"
pause 1

# Helm lint
echo ""
echo -e "${GREEN}▸ 2. Helm chart validation${NC}"
type_cmd "helm lint deploy/helm/finmind/"
pause 1

# Docker compose up
echo ""
echo -e "${GREEN}▸ 3. Docker Compose — full stack deploy${NC}"
type_cmd "cp .env.example .env"
type_cmd "docker compose up -d --build"
pause 3

# Wait for healthy
echo ""
echo -e "${GREEN}▸ 4. Waiting for services to be healthy...${NC}"
pause 15
type_cmd "docker compose ps"
pause 1

# Health checks
echo ""
echo -e "${GREEN}▸ 5. Health checks${NC}"
type_cmd "curl -s http://localhost:8000/health | python3 -m json.tool"
type_cmd "curl -sI http://localhost:5173 | head -5"
type_cmd "docker compose exec redis redis-cli ping"
type_cmd "docker compose exec postgres pg_isready -U finmind"
pause 1

# Backend logs
echo ""
echo -e "${GREEN}▸ 6. Backend logs — DB init + gunicorn workers${NC}"
type_cmd "docker compose logs backend --tail 15"
pause 1

# Auth flow
echo ""
echo -e "${GREEN}▸ 7. Auth flow — register + login${NC}"
type_cmd "curl -s -X POST http://localhost:8000/auth/register -H 'Content-Type: application/json' -d '{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}' | python3 -m json.tool"
type_cmd "curl -s -X POST http://localhost:8000/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}' | python3 -m json.tool"
pause 1

# Monitoring
echo ""
echo -e "${GREEN}▸ 8. Monitoring stack${NC}"
type_cmd "curl -sI http://localhost:9090 | head -3"
type_cmd "curl -sI http://localhost:3000 | head -3"
pause 1

# Deploy script preview
echo ""
echo -e "${GREEN}▸ 9. Interactive deploy script (14 platforms)${NC}"
type_cmd "head -28 scripts/deploy.sh"
pause 1

# Clean shutdown
echo ""
echo -e "${GREEN}▸ 10. Clean shutdown${NC}"
type_cmd "docker compose down"
pause 1

echo ""
echo -e "${GREEN}${BOLD}✅ All checks passed — deployment verified end-to-end!${NC}"
echo ""
