# Deploy FinMind on DigitalOcean Droplet

## Quick Deploy

### 1. Create Droplet
```bash
doctl compute droplet create finmind \
  --image ubuntu-24-04-x64 \
  --size s-2vcpu-4gb \
  --region nyc1 \
  --ssh-keys <your-ssh-key-id>
```

### 2. Run Setup Script
```bash
ssh root@<droplet-ip> 'bash -s' < deploy/digitalocean/droplet/setup.sh
```

This installs Docker, clones FinMind, creates `.env`, and starts all services.

## Manual Setup

```bash
ssh root@<droplet-ip>
git clone https://github.com/rohitdash08/FinMind.git /opt/finmind
cd /opt/finmind
cp .env.example .env
# Edit .env with your settings
docker compose up -d --build
```

## Verify

- Frontend: `http://<droplet-ip>:5173`
- Backend: `http://<droplet-ip>:8080/health`
- Grafana: `http://<droplet-ip>:3000`
