# Deploy FinMind to DigitalOcean Droplet

## One-Command Setup
```bash
# SSH into your Droplet, then:
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/platforms/digitalocean-droplet/setup.sh | bash
```

## Manual Setup
1. Create a Droplet (Ubuntu 22.04, 2GB+ RAM recommended)
2. SSH into the Droplet
3. Clone the repo: `git clone https://github.com/rohitdash08/FinMind.git /opt/finmind`
4. Copy and edit env: `cp .env.example .env && nano .env`
5. Start: `docker compose -f docker-compose.prod.yml up -d`
