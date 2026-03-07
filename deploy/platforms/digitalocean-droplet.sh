#!/usr/bin/env bash
# DigitalOcean Droplet one-command deploy
# Usage: curl -sSL <raw-url> | bash
# Or: ssh root@your-droplet 'bash -s' < deploy/platforms/digitalocean-droplet.sh
set -euo pipefail

echo "=== FinMind — DigitalOcean Droplet Setup ==="

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

# Install Docker Compose plugin if not present
if ! docker compose version &>/dev/null; then
  echo "Installing Docker Compose plugin..."
  apt-get update && apt-get install -y docker-compose-plugin
fi

# Clone repo
INSTALL_DIR="/opt/finmind"
if [ ! -d "$INSTALL_DIR" ]; then
  git clone --depth 1 https://github.com/rohitdash08/FinMind.git "$INSTALL_DIR"
else
  cd "$INSTALL_DIR" && git pull --ff-only
fi

cd "$INSTALL_DIR"

# Create .env from example if missing
if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a random JWT secret
  JWT=$(openssl rand -hex 32)
  PG_PASS=$(openssl rand -hex 16)
  sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT/" .env
  sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$PG_PASS/" .env
  echo "Generated .env with random secrets. Edit /opt/finmind/.env to add API keys."
fi

# Deploy
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "=== FinMind is running ==="
echo "Backend: http://$(hostname -I | awk '{print $1}'):8000/health"
echo "Frontend: http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Edit /opt/finmind/.env to configure API keys, then restart:"
echo "  cd /opt/finmind && docker compose -f docker-compose.prod.yml up -d"
