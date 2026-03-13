# DigitalOcean Deployment Guide

## Option A: App Platform

### Prerequisites
- `doctl` CLI installed and authenticated
- GitHub repo connected to DigitalOcean

### Steps

1. **Deploy from spec:**
   ```bash
   doctl apps create --spec .do/app.yaml
   ```
   Or connect the repo via the [DigitalOcean dashboard](https://cloud.digitalocean.com/apps) — it auto-detects `.do/app.yaml`.

2. **Set environment variables** in the dashboard:
   - `JWT_SECRET` — generate with `openssl rand -hex 32`
   - `GEMINI_API_KEY` — optional, for AI features
   - `DATABASE_URL` and `REDIS_URL` are auto-populated from managed add-ons

3. **Note on Redis:** DO App Platform doesn't have managed Redis. Options:
   - Use a [DigitalOcean Managed Redis](https://cloud.digitalocean.com/databases) cluster and set `REDIS_URL` manually
   - Use Upstash Redis (free tier available)

## Option B: Droplet

### Prerequisites
- A fresh Ubuntu 22.04+ droplet (1GB+ RAM recommended)
- SSH access as root

### Steps

1. **SSH into your droplet and run:**
   ```bash
   curl -sSL https://raw.githubusercontent.com/rohitdash08/FinMind/main/deploy/droplet/setup.sh | bash
   ```

2. **Edit configuration:**
   ```bash
   nano /opt/finmind/.env
   docker compose -f /opt/finmind/docker-compose.yml restart
   ```

3. **Endpoints:**
   - Frontend: `http://<droplet-ip>:5173`
   - Backend: `http://<droplet-ip>:8000/health`
   - Grafana: `http://<droplet-ip>:3000`

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
