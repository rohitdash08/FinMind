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
   - `VITE_API_URL` — set on the frontend static site to the backend service URL

3. **Note on Redis:** DO App Platform doesn't have managed Redis in app specs. Options:
   - Use a [DigitalOcean Managed Redis](https://cloud.digitalocean.com/databases) cluster and set `REDIS_URL` on the backend service
   - Use [Upstash Redis](https://upstash.com) (free tier available)

4. **Note on DATABASE_URL:** DigitalOcean provides `postgres://` connection strings.
   The backend automatically converts these to the `postgresql+psycopg2://` format
   required by SQLAlchemy.

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
   - Frontend: `http://<droplet-ip>:8080` (via nginx)
   - Backend: `http://<droplet-ip>:8000/health`
   - Grafana: `http://<droplet-ip>:3000`

## Verification
1. Frontend loads in browser
2. `GET /health` returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
