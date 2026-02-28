#!/usr/bin/env bash
# FinMind — DigitalOcean Droplet one-click setup
# Run as root on a fresh Ubuntu 22.04+ droplet:
#   curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/droplet/setup.sh | bash
set -euo pipefail

echo "=== FinMind Droplet Setup ==="

# Install Docker
if ! command -v docker &>/dev/null; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

# Install Docker Compose plugin
if ! docker compose version &>/dev/null; then
  echo "Installing Docker Compose..."
  apt-get update && apt-get install -y docker-compose-plugin
fi

# Clone repo
INSTALL_DIR="/opt/finmind"
if [ ! -d "$INSTALL_DIR" ]; then
  git clone https://github.com/rohitdash08/FinMind.git "$INSTALL_DIR"
else
  cd "$INSTALL_DIR" && git pull
fi
cd "$INSTALL_DIR"

# Create .env from example if not exists
if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a random JWT secret
  JWT=$(openssl rand -hex 32)
  sed -i "s/JWT_SECRET=\"change-me\"/JWT_SECRET=\"$JWT\"/" .env
  echo "Created .env with random JWT_SECRET. Edit /opt/finmind/.env for other settings."
fi

# Start services
docker compose up -d

echo ""
echo "=== FinMind is starting! ==="
echo "Frontend:  http://$(curl -s ifconfig.me):5173"
echo "Backend:   http://$(curl -s ifconfig.me):8000/health"
echo "Grafana:   http://$(curl -s ifconfig.me):3000"
echo ""
echo "Edit /opt/finmind/.env and run 'docker compose restart' to update config."
