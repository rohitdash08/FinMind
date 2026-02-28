# FinMind — AI-Powered Budget & Bill Tracking

FinMind helps users control spending, track bills, and get smart financial insights. Built for free-tier friendly deployment with scalable architecture.

## 🚀 One-Click Deploy

### Full Stack
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/finmind?referralCode=finmind)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/rohitdash08/FinMind)
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/rohitdash08/FinMind)
[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/rohitdash08/FinMind/tree/main)

### Frontend Only
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app)
[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind)

> 📖 **Full deployment guide**: [DEPLOYMENT.md](DEPLOYMENT.md) | **Platform configs**: [deploy/](deploy/)

## System Architecture

```mermaid
flowchart LR
  subgraph Client
    A[React + Vite + TS]
    A -->|JWT| LS[(LocalStorage)]
  end

  subgraph Edge
    CDN[CDN/Vercel Edge]
  end

  subgraph Backend[Flask API]
    API[Flask + Gunicorn]
    JWT[PyJWT]
    AI[Insights Service]
    SCH[Scheduler/APScheduler]
  end

  subgraph Data
    PG[(PostgreSQL)]
    RD[(Redis)]
  end

  subgraph ThirdParty
    TW[Twilio WhatsApp]
    SMTP[Email Provider]
    OAI[OpenAI or Local ML]
  end

  A -->|HTTPS| CDN --> API
  API -->|ORM| PG
  API -->|Cache| RD
  API -->|JWT verify| JWT
  API -->|reminder jobs| SCH
  SCH --> TW
  SCH --> SMTP
  AI --> OAI
```

## PostgreSQL Schema (DDL)
See `backend/app/db/schema.sql`. Key tables:
- users, categories, expenses, bills, reminders
- ad_impressions, subscription_plans, user_subscriptions
- refresh_tokens (optional if rotating), audit_logs

## Redis Caching Policy
- Keys
  - `user:{id}:monthly_summary:{yyyy-mm}` — 30 min TTL
  - `user:{id}:categories` — 24h TTL
  - `user:{id}:upcoming_bills` — 15 min TTL
  - `insights:{id}` — 24h TTL (invalidate on new expense/bill)
- Invalidation
  - On expense/bill create/update/delete -> delete affected monthly_summary, upcoming_bills, insights
- Rate limiting (optional): `rl:{userId}:{endpoint}:{minute}` with short TTL

## API Endpoints
OpenAPI: `backend/app/openapi.yaml`
- Auth: `/auth/register`, `/auth/login`, `/auth/refresh`
- Expenses: CRUD `/expenses`
- Bills: CRUD `/bills`, pay/mark `/bills/{id}/pay`
- Reminders: CRUD `/reminders`, trigger `/reminders/run`
- Insights: `/insights/monthly`, `/insights/budget-suggestion`

## MVP UI/UX Plan
- Auth screens: register/login.
- Dashboard:
  - Monthly spend chart, category breakdown donut.
  - Upcoming bills list with due dates and pay status.
  - AI budget suggestion card.
- Expenses page: add expense (amount, category, notes, date), list & filter.
- Bills page: create bill (name, amount, cadence, due date, channel), toggle WhatsApp/email.
- Settings: profile, categories, reminders default channel, export (premium).

## Monetization Plan
- Free: ads in dashboard and list pages (lightweight, non-intrusive). Record impressions in `ad_impressions`.
- Premium ($/mo): CSV/Excel export, multi-device sync, priority insights, remove ads.
- Payments stubbed; swap in Stripe when moving off free tier.

## Organic Marketing Strategies
- Content: budgeting tips, “FinMind monthly challenge” on socials.
- SEO: landing with calculators (50/30/20, debt snowball), schema markup.
- Communities: Reddit PF, indie hackers build-in-public.
- Referral: give 1 month premium for inviting 3 friends.

## Project Structure
```
finmind/
  backend/
    app/
      __init__.py
      config.py
      extensions.py
      models.py
      routes/
        __init__.py
        auth.py
        expenses.py
        bills.py
        reminders.py
        insights.py
      services/
        __init__.py
        ai.py
        cache.py
        reminders.py
      db/
        schema.sql
      openapi.yaml
    wsgi.py
    requirements.txt
    Dockerfile
  frontend/
    index.html
    src/
      main.tsx
      App.tsx
      components/
        AdBanner.tsx
        Charts.tsx
      pages/
        Dashboard.tsx
        Expenses.tsx
        Bills.tsx
        Settings.tsx
    package.json
    tsconfig.json
    vite.config.ts
    Dockerfile
  .github/
    workflows/
      ci.yml
  docker-compose.yml
  .env.example
```

## Deployment

FinMind supports one-click deployment to all major platforms:

| Platform | Type | Config | Free Tier |
|----------|------|--------|-----------|
| [Railway](deploy/railway/README.md) | PaaS | `railway.json` | ✅ $5/mo |
| [Render](deploy/render/README.md) | PaaS | `render.yaml` | ✅ |
| [Fly.io](deploy/fly/README.md) | PaaS | `fly.toml` | ✅ |
| [Heroku](deploy/heroku/README.md) | PaaS | `heroku.yml` | ❌ |
| [DigitalOcean](deploy/digitalocean/README.md) | PaaS | `.do/app.yaml` | ❌ |
| [AWS ECS](deploy/aws/README.md) | IaaS | `ecs-task-definition.json` | ❌ |
| [GCP Cloud Run](deploy/gcp/README.md) | PaaS | `cloudrun.yaml` | ✅ |
| [Azure Container Apps](deploy/azure/README.md) | PaaS | `container-app.yaml` | ✅ |
| [Kubernetes](deploy/helm/README.md) | K8s | Helm chart | N/A |
| Docker Compose | Self-hosted | `docker-compose.prod.yml` | N/A |

### Quick Deploy Options

**Docker Compose (Production):**
```bash
cp .env.example .env.production
docker compose -f docker-compose.prod.yml up -d
```

**Kubernetes (Helm):**
```bash
helm install finmind deploy/helm/finmind \
  --namespace finmind --create-namespace \
  --set secrets.jwtSecret=$(openssl rand -hex 32)
```

**Local K8s Development (Tilt):**
```bash
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
tilt up
```

📖 See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive deployment guide.

## Local Development
1) Prereqs: Docker, Docker Compose, Node 20+, Python 3.11+
2) Copy env: `cp .env.example .env` and fill secrets
3) Start: `docker compose up --build`
4) Frontend at http://localhost:5173, Backend at http://localhost:8000
5) Observability stack (dev compose) is included:
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090
   - Loki: http://localhost:3100
   - Nginx proxy: http://localhost:8080 (status at `/nginx_status`)

### Backend Test Runner (No local pytest setup required)
- PowerShell (Windows):
  - `./scripts/test-backend.ps1`
  - single file: `./scripts/test-backend.ps1 tests/test_dashboard.py`
- POSIX shell:
  - `sh ./scripts/test-backend.sh`
  - single file: `sh ./scripts/test-backend.sh tests/test_dashboard.py`

## Testing & CI
- Backend: pytest, flake8, black. Frontend: vitest, eslint.
- GitHub Actions `ci.yml` runs lint, tests, and builds both apps; optional docker build.

## Monitoring (Grafana OSS)
- Backend exposes Prometheus metrics at `/metrics` with:
  - request count by endpoint/status
  - request duration histograms (latency, including dashboard p95 KPI)
  - reminder event counters (engagement KPI)
- Logs are emitted as JSON with `request_id` and shipped to Loki via Promtail.
- Pre-provisioned Grafana dashboard: `FinMind Operations and KPI`.

## Contribution Policy
- See `CONTRIBUTING.md` for fork-first contribution flow and PR requirements.

## Notes on Free-Tier Reminders
- Primary: schedule via APScheduler in-process with persistence in Postgres (job table) and a simple daily trigger. Alternatively, use Railway/Render cron to hit `/reminders/run`.
- Twilio WhatsApp free trial supports sandbox; email via SMTP (e.g., SendGrid free tier).

## Security & Scalability
- JWT access/refresh, secure cookies OR Authorization header.
- RBAC-ready via roles on `users.role`.
- N+1 avoided via SQLAlchemy eager loading.
- Redis caching for hot paths to cut DB load.
- 12-factor app env config; stateless API.

---

MIT Licensed. Built with ❤️.
