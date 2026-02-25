#!/usr/bin/env bash
# FinMind — DigitalOcean Droplet One-Click Setup
# ────────────────────────────────────────────────
# Usage:
#   curl -sSL https://raw.githubusercontent.com/your-org/FinMind/main/deploy/digitalocean/scripts/droplet-setup.sh | bash
#
# Or SSH into your droplet and run:
#   bash droplet-setup.sh
#
# Tested on: Ubuntu 22.04 / 24.04 LTS
# Minimum: 2 vCPU, 2 GB RAM ($12/mo droplet)

set -euo pipefail

# ── Configuration ──────────────────────────────────
APP_DIR="/opt/finmind"
REPO_URL="${FINMIND_REPO:-https://github.com/your-org/FinMind.git}"
BRANCH="${FINMIND_BRANCH:-main}"
DOMAIN="${FINMIND_DOMAIN:-}"
EMAIL="${CERTBOT_EMAIL:-}"

echo "╔══════════════════════════════════════════╗"
echo "║   FinMind — Droplet One-Click Setup      ║"
echo "╚══════════════════════════════════════════╝"

# ── 1. System Update ──────────────────────────────
echo "→ Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# ── 2. Install Docker ─────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "→ Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    echo "→ Docker already installed."
fi

# ── 3. Install Docker Compose Plugin ──────────────
if ! docker compose version &>/dev/null; then
    echo "→ Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

# ── 4. Firewall ───────────────────────────────────
echo "→ Configuring UFW firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 5. Clone Repository ──────────────────────────
if [ -d "$APP_DIR" ]; then
    echo "→ Updating existing installation..."
    cd "$APP_DIR"
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    echo "→ Cloning FinMind repository..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ── 6. Environment File ──────────────────────────
if [ ! -f .env ]; then
    echo "→ Creating .env from template..."
    cp .env.example .env

    # Generate secure secrets
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s|JWT_SECRET=\"change-me\"|JWT_SECRET=\"${JWT_SECRET}\"|" .env

    # Use strong random passwords for PostgreSQL
    PG_PASS=$(openssl rand -hex 16)
    sed -i "s|POSTGRES_PASSWORD=\"finmind\"|POSTGRES_PASSWORD=\"${PG_PASS}\"|" .env
    sed -i "s|postgresql+psycopg2://finmind:finmind@|postgresql+psycopg2://finmind:${PG_PASS}@|" .env

    echo "→ .env created with generated secrets."
    echo "  ⚠  Edit /opt/finmind/.env to add API keys (GEMINI_API_KEY, etc.)"
fi

# ── 7. Build & Start ─────────────────────────────
echo "→ Building and starting services..."
docker compose build --no-cache
docker compose up -d postgres redis
echo "→ Waiting for PostgreSQL to be ready..."
sleep 10
docker compose up -d

# ── 8. Optional: SSL with Certbot ─────────────────
if [ -n "$DOMAIN" ] && [ -n "$EMAIL" ]; then
    echo "→ Setting up SSL for $DOMAIN..."
    apt-get install -y -qq certbot python3-certbot-nginx nginx

    # Create nginx site config
    cat > /etc/nginx/sites-available/finmind <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

    ln -sf /etc/nginx/sites-available/finmind /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx

    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL"
    echo "→ SSL configured for $DOMAIN"
else
    echo "→ Skipping SSL (set FINMIND_DOMAIN and CERTBOT_EMAIL to enable)"
fi

# ── 9. Systemd Service ───────────────────────────
cat > /etc/systemd/system/finmind.service <<EOF
[Unit]
Description=FinMind Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable finmind.service

# ── Done ──────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ FinMind deployed successfully!       ║"
echo "╠══════════════════════════════════════════╣"
echo "║   Backend:  http://$(hostname -I | awk '{print $1}'):8000    ║"
echo "║   Frontend: http://$(hostname -I | awk '{print $1}'):5173    ║"
echo "║   Nginx:    http://$(hostname -I | awk '{print $1}'):8080    ║"
echo "║   Grafana:  http://$(hostname -I | awk '{print $1}'):3000    ║"
echo "╠══════════════════════════════════════════╣"
echo "║   Config:   /opt/finmind/.env            ║"
echo "║   Logs:     docker compose logs -f       ║"
echo "║   Restart:  systemctl restart finmind    ║"
echo "╚══════════════════════════════════════════╝"
