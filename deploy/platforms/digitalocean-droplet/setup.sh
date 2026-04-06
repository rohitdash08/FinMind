#!/bin/bash
set -euo pipefail

# FinMind - DigitalOcean Droplet Setup Script
# Run: curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean-droplet/setup.sh | bash

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
if [ ! -d "/opt/finmind" ]; then
    git clone https://github.com/rohitdash08/FinMind.git /opt/finmind
fi

cd /opt/finmind

# Create .env from example
if [ ! -f ".env" ]; then
    cp .env.example .env
    # Generate random secrets
    sed -i "s/JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env
    echo "Created .env file. Please review and update values."
fi

# Start services
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "=== FinMind is starting ==="
echo "Frontend: http://$(hostname -I | awk '{print $1}')"
echo "Backend:  http://$(hostname -I | awk '{print $1}')/api/health"
echo ""
echo "Run 'docker compose -f docker-compose.prod.yml logs -f' to view logs"
