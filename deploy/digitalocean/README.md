# DigitalOcean Deployment

## App Platform (One-Click)

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main)

## CLI Deployment

### Prerequisites
```bash
# Install doctl
brew install doctl  # or snap install doctl
doctl auth init
```

### Deploy
```bash
doctl apps create --spec deploy/digitalocean/.do/app.yaml
```

### Update
```bash
doctl apps update <app-id> --spec deploy/digitalocean/.do/app.yaml
```

## Droplet Deployment (Manual)

### 1. Create Droplet
```bash
doctl compute droplet create finmind \
  --image docker-20-04 \
  --size s-2vcpu-2gb \
  --region nyc1 \
  --ssh-keys <your-key-id>
```

### 2. SSH and Deploy
```bash
ssh root@<droplet-ip>

# Clone and deploy
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind
cp .env.example .env
# Edit .env with your secrets
docker compose -f docker-compose.prod.yml up -d
```

## Managed Databases

For production, use DigitalOcean Managed Databases:

```bash
# PostgreSQL
doctl databases create finmind-db \
  --engine pg \
  --size db-s-1vcpu-1gb \
  --region nyc1

# Redis
doctl databases create finmind-redis \
  --engine redis \
  --size db-s-1vcpu-1gb \
  --region nyc1
```

## Pricing

- App Platform Basic: $5/month
- Dev Database (PG): $12/month
- Dev Database (Redis): $12/month
- Droplet (s-2vcpu-2gb): $18/month

## Monitoring

```bash
doctl apps logs <app-id> --follow
doctl apps list-deployments <app-id>
```
