#!/bin/bash
# FinMind DigitalOcean Droplet Setup Script
# Run on a fresh Ubuntu 22.04+ droplet
#
# Usage: curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/droplet/setup.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[FinMind]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root (sudo)"
fi

log "Starting FinMind installation..."

# Update system
log "Updating system packages..."
apt-get update && apt-get upgrade -y

# Install Docker
log "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    success "Docker installed"
else
    success "Docker already installed"
fi

# Install Docker Compose
log "Installing Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
    success "Docker Compose installed"
else
    success "Docker Compose already installed"
fi

# Create app directory
APP_DIR="/opt/finmind"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Clone repository
log "Cloning FinMind repository..."
if [ -d "$APP_DIR/.git" ]; then
    git pull origin main
else
    git clone https://github.com/rohitdash08/FinMind.git .
fi
success "Repository cloned"

# Setup environment
log "Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp .env.example .env
    
    # Generate secrets
    JWT_SECRET=$(openssl rand -hex 32)
    POSTGRES_PASSWORD=$(openssl rand -base64 16 | tr -d '=+/')
    
    # Update .env file
    sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" .env
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
    
    warn "Environment file created. Edit /opt/finmind/.env to add your API keys."
fi

# Setup Nginx for SSL
log "Installing Nginx and Certbot..."
apt-get install -y nginx certbot python3-certbot-nginx

# Create Nginx config
log "Configuring Nginx..."
cat > /etc/nginx/sites-available/finmind << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

ln -sf /etc/nginx/sites-available/finmind /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Setup firewall
log "Configuring firewall..."
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Create systemd service
log "Creating systemd service..."
cat > /etc/systemd/system/finmind.service << EOF
[Unit]
Description=FinMind Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker compose -f docker-compose.prod.yml restart

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable finmind

# Start application
log "Starting FinMind..."
docker compose -f docker-compose.prod.yml up -d

success "FinMind installation complete!"
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                    FinMind Installed!                        ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Application: http://$(curl -s ifconfig.me)                   "
echo "║                                                               ║"
echo "║  Next steps:                                                  ║"
echo "║  1. Edit /opt/finmind/.env with your API keys                ║"
echo "║  2. Set your domain in Nginx config                          ║"
echo "║  3. Run: certbot --nginx -d yourdomain.com                   ║"
echo "║  4. Restart: systemctl restart finmind                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
log "Logs: docker compose -f docker-compose.prod.yml logs -f"
log "Status: docker compose -f docker-compose.prod.yml ps"
