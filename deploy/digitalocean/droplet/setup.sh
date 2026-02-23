#!/bin/bash
set -euo pipefail

# FinMind - DigitalOcean Droplet Setup Script
# Usage: ssh root@<droplet-ip> 'bash -s' < deploy/digitalocean/droplet/setup.sh
# Or:    curl -sSL <raw-url> | bash

echo "🚀 Setting up FinMind on DigitalOcean Droplet..."

# System updates
apt-get update -y && apt-get upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
  echo "📦 Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
fi

# Install Docker Compose
if ! command -v docker compose &> /dev/null; then
  apt-get install -y docker-compose-plugin
fi

# Clone repo
APP_DIR="/opt/finmind"
if [ ! -d "$APP_DIR" ]; then
  echo "📥 Cloning FinMind..."
  git clone https://github.com/rohitdash08/FinMind.git "$APP_DIR"
else
  echo "📥 Updating FinMind..."
  cd "$APP_DIR" && git pull
fi

cd "$APP_DIR"

# Create .env if not exists
if [ ! -f .env ]; then
  echo "🔐 Creating .env..."
  cp .env.example .env
  # Generate secure JWT secret
  sed -i "s/JWT_SECRET=\"change-me\"/JWT_SECRET=\"$(openssl rand -hex 32)\"/" .env
  # Set production API URL
  DROPLET_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || hostname -I | awk '{print $1}')
  sed -i "s|VITE_API_URL=.*|VITE_API_URL=http://${DROPLET_IP}:8080|" .env
  echo "  → .env created with IP: $DROPLET_IP"
fi

# Setup firewall
echo "🔒 Configuring firewall..."
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 8080/tcp # Nginx proxy
ufw allow 5173/tcp # Frontend dev
ufw --force enable

# Start services
echo "🐳 Starting FinMind..."
docker compose up -d --build

# Wait for health
echo "⏳ Waiting for services..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ Backend healthy!"
    break
  fi
  sleep 2
done

echo ""
echo "🎉 FinMind is ready!"
echo "   Frontend: http://${DROPLET_IP:-localhost}:5173"
echo "   Backend:  http://${DROPLET_IP:-localhost}:8080"
echo "   Health:   http://${DROPLET_IP:-localhost}:8080/health"
echo ""
echo "📊 Monitoring:"
echo "   Grafana:    http://${DROPLET_IP:-localhost}:3000"
echo "   Prometheus: http://${DROPLET_IP:-localhost}:9090"
