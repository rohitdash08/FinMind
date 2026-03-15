#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# FinMind — DigitalOcean Droplet Setup Script
#
# Sets up a fresh Ubuntu 22.04+ droplet with Docker, Docker Compose,
# clones the repo, and starts all services.
#
# Usage:
#   1. Create a Droplet (Ubuntu 22.04, 2GB+ RAM recommended)
#   2. SSH in: ssh root@<droplet-ip>
#   3. Run:
#      curl -sSL https://raw.githubusercontent.com/your-org/FinMind/main/deploy/digitalocean/droplet-setup.sh | bash
#      — or —
#      wget -qO- https://raw.githubusercontent.com/your-org/FinMind/main/deploy/digitalocean/droplet-setup.sh | bash
#
# Environment variables (set before running, or you'll be prompted):
#   FINMIND_REPO        — Git repo URL (default: https://github.com/your-org/FinMind.git)
#   JWT_SECRET          — JWT signing secret (auto-generated if empty)
#   GEMINI_API_KEY      — Google Gemini API key
#   DOMAIN              — Domain name for TLS (optional)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────
FINMIND_REPO="${FINMIND_REPO:-https://github.com/your-org/FinMind.git}"
INSTALL_DIR="/opt/finmind"
COMPOSE_VERSION="2.24.5"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[FinMind]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()   { echo -e "${RED}[ERROR ]${NC} $*" >&2; exit 1; }

# ── Preflight Checks ────────────────────────────────────────
log "Starting FinMind droplet setup..."

if [[ "$(id -u)" -ne 0 ]]; then
  err "This script must be run as root."
fi

# Detect OS
if ! grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
  warn "This script is designed for Ubuntu. Proceeding anyway..."
fi

# ── 1. System Updates ───────────────────────────────────────
log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  ufw \
  fail2ban \
  unattended-upgrades \
  htop \
  jq
ok "System packages updated"

# ── 2. Docker Installation ──────────────────────────────────
log "Installing Docker..."
if command -v docker &>/dev/null; then
  ok "Docker already installed: $(docker --version)"
else
  # Add Docker GPG key
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  # Add Docker repo
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  ok "Docker installed: $(docker --version)"
fi

# Enable and start Docker
systemctl enable docker
systemctl start docker

# ── 3. Firewall Setup ───────────────────────────────────────
log "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ok "Firewall configured (SSH, HTTP, HTTPS)"

# ── 4. Fail2Ban ─────────────────────────────────────────────
log "Configuring fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban
ok "fail2ban active"

# ── 5. Clone Repository ─────────────────────────────────────
log "Cloning FinMind repository..."
if [[ -d "$INSTALL_DIR" ]]; then
  warn "$INSTALL_DIR exists — pulling latest..."
  cd "$INSTALL_DIR"
  git pull origin main
else
  git clone "$FINMIND_REPO" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi
ok "Repository ready at $INSTALL_DIR"

# ── 6. Environment Configuration ────────────────────────────
log "Setting up environment variables..."

ENV_FILE="$INSTALL_DIR/.env"

# Generate JWT_SECRET if not set
if [[ -z "${JWT_SECRET:-}" ]]; then
  JWT_SECRET=$(openssl rand -hex 64)
  warn "Auto-generated JWT_SECRET"
fi

# Prompt for GEMINI_API_KEY if not set
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  warn "GEMINI_API_KEY not set. Set it in $ENV_FILE after setup."
  GEMINI_API_KEY="CHANGE_ME"
fi

cat > "$ENV_FILE" <<EOF
# FinMind Environment Configuration
# Generated on $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Database ─────────────────────────────────────────────────
DATABASE_URL=postgresql://finmind:finmind_secure_password@postgres:5432/finmind
POSTGRES_DB=finmind
POSTGRES_USER=finmind
POSTGRES_PASSWORD=finmind_secure_password

# ── Redis ────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── Application ─────────────────────────────────────────────
JWT_SECRET=${JWT_SECRET}
GEMINI_API_KEY=${GEMINI_API_KEY}
GEMINI_MODEL=gemini-pro
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

# ── Frontend ────────────────────────────────────────────────
VITE_API_URL=http://localhost:8000
EOF

chmod 600 "$ENV_FILE"
ok "Environment file created at $ENV_FILE"

# ── 7. Docker Compose Production File ───────────────────────
log "Creating production docker-compose file..."

cat > "$INSTALL_DIR/docker-compose.prod.yml" <<'COMPOSE'
version: "3.9"

services:
  # ── PostgreSQL ─────────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - finmind

  # ── Redis ──────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - finmind

  # ── Backend API ────────────────────────────────────────────
  backend:
    build:
      context: .
      dockerfile: packages/backend/Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
        reservations:
          memory: 256M
          cpus: "0.25"
    networks:
      - finmind

  # ── Frontend ───────────────────────────────────────────────
  frontend:
    build:
      context: ./app
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.5"
        reservations:
          memory: 128M
          cpus: "0.1"
    networks:
      - finmind

volumes:
  pgdata:
    driver: local
  redisdata:
    driver: local

networks:
  finmind:
    driver: bridge
COMPOSE

ok "Production compose file created"

# ── 8. Systemd Service ──────────────────────────────────────
log "Creating systemd service..."

cat > /etc/systemd/system/finmind.service <<EOF
[Unit]
Description=FinMind Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml --env-file .env up -d --build
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker compose -f docker-compose.prod.yml --env-file .env up -d --build
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable finmind.service
ok "Systemd service created and enabled"

# ── 9. Log Rotation ─────────────────────────────────────────
log "Configuring Docker log rotation..."
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker
ok "Docker log rotation configured"

# ── 10. Start Services ──────────────────────────────────────
log "Building and starting services..."
cd "$INSTALL_DIR"
docker compose -f docker-compose.prod.yml --env-file .env up -d --build

# Wait for services
log "Waiting for services to be healthy..."
sleep 15

# ── 11. Health Check ────────────────────────────────────────
log "Running health checks..."

check_service() {
  local name="$1" url="$2"
  if curl -sf --max-time 10 "$url" > /dev/null 2>&1; then
    ok "$name is healthy ($url)"
  else
    warn "$name not responding yet — may still be starting ($url)"
  fi
}

check_service "Backend"  "http://localhost:8000/health"
check_service "Frontend" "http://localhost:80/"

# ── Summary ──────────────────────────────────────────────────
DROPLET_IP=$(curl -sf --max-time 5 http://checkip.amazonaws.com || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  FinMind Deployment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Frontend:    http://${DROPLET_IP}/"
echo -e "  Backend API: http://${DROPLET_IP}:8000/"
echo -e "  Health:      http://${DROPLET_IP}:8000/health"
echo ""
echo -e "  Install dir: ${INSTALL_DIR}"
echo -e "  Env file:    ${INSTALL_DIR}/.env"
echo ""
echo -e "${YELLOW}  Next steps:${NC}"
echo -e "  1. Update GEMINI_API_KEY in ${INSTALL_DIR}/.env"
echo -e "  2. Change POSTGRES_PASSWORD in ${INSTALL_DIR}/.env"
echo -e "  3. Set up a domain and TLS (e.g., with Caddy or Certbot)"
echo -e "  4. Restart: systemctl restart finmind"
echo ""
echo -e "  Useful commands:"
echo -e "    docker compose -f ${INSTALL_DIR}/docker-compose.prod.yml logs -f"
echo -e "    docker compose -f ${INSTALL_DIR}/docker-compose.prod.yml ps"
echo -e "    systemctl status finmind"
echo ""
