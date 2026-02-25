# FinMind — DigitalOcean Deployment

## Option 1: App Platform (Managed PaaS)

One-click deploy with auto-managed PostgreSQL and Redis.

### Quick Deploy

```bash
doctl apps create --spec deploy/digitalocean/.do/app.yaml
```

Or in the DO console: Apps → Create App → From Spec → upload `deploy/digitalocean/.do/app.yaml`

### Features
- Auto-deploy on push
- Managed PostgreSQL 16 + Redis 7
- Built-in health checks
- Auto-scaling

---

## Option 2: Droplet (Self-Hosted)

One-click setup on an Ubuntu Droplet. Minimum: 2 vCPU / 2 GB RAM ($12/mo).

### Quick Deploy

```bash
# SSH into your Droplet and run:
curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/digitalocean/scripts/droplet-setup.sh | bash
```

### With Custom Domain + SSL

```bash
FINMIND_DOMAIN=finmind.example.com CERTBOT_EMAIL=you@example.com bash droplet-setup.sh
```

### What the Script Does
1. Installs Docker + Docker Compose
2. Configures UFW firewall (SSH, HTTP, HTTPS)
3. Clones the repo to `/opt/finmind`
4. Generates secure secrets (JWT, DB password)
5. Builds and starts all services
6. Optionally configures Nginx + Let's Encrypt SSL
7. Creates systemd service for auto-start on reboot

## Files

| File | Description |
|------|-------------|
| `.do/app.yaml` | App Platform spec |
| `scripts/droplet-setup.sh` | Droplet one-click setup script |

## Cost Estimate

| Option | Estimated Monthly Cost |
|--------|----------------------|
| App Platform (basic) | ~$17 |
| Droplet (2 vCPU/2GB) | ~$12 |
