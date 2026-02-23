# Deploy FinMind on Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

## One-Click Setup

### 1. Create Services

In your Railway project, create **4 services**:

#### PostgreSQL (Database)
- Click **+ New** → **Database** → **PostgreSQL**
- Note the `DATABASE_URL` from the service variables

#### Redis
- Click **+ New** → **Database** → **Redis**
- Note the `REDIS_URL` from the service variables

#### Backend
- Click **+ New** → **GitHub Repo** → Select your FinMind fork
- **Settings**:
  - Root Directory: `/`
  - Dockerfile Path: `packages/backend/Dockerfile`
  - Start Command: `sh -c 'python -m flask --app wsgi:app init-db && gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT wsgi:app'`
- **Variables**:
  ```
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  REDIS_URL=${{Redis.REDIS_URL}}
  JWT_SECRET=<generate-a-secret>
  PORT=8000
  ```
- **Networking**: Generate a domain (e.g., `finmind-api.up.railway.app`)

#### Frontend
- Click **+ New** → **GitHub Repo** → Select your FinMind fork
- **Settings**:
  - Root Directory: `app`
  - Build Command: `npm ci && npm run build`
  - Start Command: (uses Dockerfile → nginx)
- **Variables**:
  ```
  VITE_API_URL=https://finmind-api.up.railway.app
  ```
- **Networking**: Generate a domain

### 2. Verify

- Frontend: `https://<frontend>.up.railway.app`
- Backend Health: `https://<backend>.up.railway.app/health`
- Create an account and test auth, expenses, dashboard

## CLI Deployment

```bash
# Install Railway CLI
npm i -g @railway/cli
railway login

# Create project
railway init

# Deploy backend
railway up --service backend

# Deploy frontend
cd app && railway up --service frontend
```
