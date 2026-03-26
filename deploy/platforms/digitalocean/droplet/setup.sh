#!/usr/bin/env bash
# DigitalOcean Droplet One-Line Setup
# Usage: curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean/droplet/setup.sh | bash
set -euo pipefail

echo "=========================================="
echo "  FinMind — DigitalOcean Droplet Setup"
echo "=========================================="

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (or with sudo)."
    exit 1
fi

# ─── Install Docker ───
if ! command -v docker &>/dev/null; then
    echo "[1/5] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "[1/5] Docker already installed."
fi

# ─── Install Docker Compose ───
if ! docker compose version &>/dev/null; then
    echo "[2/5] Installing Docker Compose plugin..."
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
else
    echo "[2/5] Docker Compose already installed."
fi

# ─── Clone FinMind ───
INSTALL_DIR="/opt/finmind"
if [ -d "$INSTALL_DIR" ]; then
    echo "[3/5] Updating existing installation..."
    cd "$INSTALL_DIR" && git pull
else
    echo "[3/5] Cloning FinMind..."
    git clone https://github.com/rohitdash08/FinMind.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ─── Configure Environment ───
if [ ! -f .env ]; then
    echo "[4/5] Creating .env from template..."
    cp .env.example .env
    # Generate secure JWT secret
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env
    # Generate secure postgres password
    PG_PASS=$(openssl rand -hex 16)
    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASS|" .env
    sed -i "s|postgresql+psycopg2://finmind:finmind@|postgresql+psycopg2://finmind:${PG_PASS}@|" .env
    echo "  Generated secure secrets in .env"
else
    echo "[4/5] .env already exists, keeping current config."
fi

# ─── Start Services ───
echo "[5/5] Starting FinMind..."
docker compose up -d --build

echo ""
echo "=========================================="
echo "  FinMind is running!"
echo ""
echo "  Frontend:  http://$(hostname -I | awk '{print $1}'):5173"
echo "  Backend:   http://$(hostname -I | awk '{print $1}'):8000"
echo "  Grafana:   http://$(hostname -I | awk '{print $1}'):3000"
echo ""
echo "  Manage:    cd $INSTALL_DIR && docker compose logs -f"
echo "=========================================="
