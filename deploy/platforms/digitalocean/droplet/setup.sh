#!/usr/bin/env bash
# FinMind - DigitalOcean Droplet One-Click Setup
# Usage: curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean/droplet/setup.sh | bash
set -euo pipefail

echo "=== FinMind Droplet Setup ==="

# Install Docker if not present
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    sudo systemctl enable docker
    sudo systemctl start docker
fi

# Install Docker Compose plugin if not present
if ! docker compose version &>/dev/null; then
    echo "Installing Docker Compose..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# Clone repo
INSTALL_DIR="/opt/finmind"
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR" && git pull
else
    echo "Cloning FinMind..."
    sudo git clone https://github.com/rohitdash08/FinMind.git "$INSTALL_DIR"
    sudo chown -R "$USER:$USER" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate a random JWT secret
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/JWT_SECRET=\"change-me\"/JWT_SECRET=\"$JWT_SECRET\"/" .env
    echo "Created .env file with generated JWT_SECRET"
    echo "Please edit .env to add your GEMINI_API_KEY and other settings"
fi

# Setup firewall
if command -v ufw &>/dev/null; then
    sudo ufw allow 22/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw --force enable
fi

# Build and start
echo "Building and starting FinMind..."
docker compose up -d --build

echo ""
echo "=== FinMind is starting! ==="
echo "Frontend: http://$(curl -s ifconfig.me):5173"
echo "Backend:  http://$(curl -s ifconfig.me):8000"
echo "Nginx:    http://$(curl -s ifconfig.me):8080"
echo ""
echo "To view logs: cd $INSTALL_DIR && docker compose logs -f"
echo "To stop:      cd $INSTALL_DIR && docker compose down"
