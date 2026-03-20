# Railway Deployment

## Quick Start

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?template=https://github.com/rohitdash08/FinMind)

## Manual Setup

1. Install the [Railway CLI](https://docs.railway.app/develop/cli) or use the dashboard.

2. Create a new project:
   ```bash
   railway login
   railway init
   ```

3. Add services in the Railway dashboard:
   - **PostgreSQL** — Add from the database menu
   - **Redis** — Add from the database menu
   - **Backend** — Link this repo, set root directory to `/packages/backend`
   - **Frontend** — Link this repo, set root directory to `/app`

4. Set environment variables on the backend service:
   - `DATABASE_URL` — Reference from Railway Postgres (auto-provided)
   - `REDIS_URL` — Reference from Railway Redis (auto-provided)
   - `JWT_SECRET` — Generate: `openssl rand -hex 32`
   - `LOG_LEVEL` — `INFO`

5. Set environment variables on the frontend service:
   - `VITE_API_URL` — Set to the backend service's public URL

6. Deploy:
   ```bash
   railway up
   ```

## Notes

- Railway auto-detects Dockerfiles in each service root.
- The `railway.json` in this directory configures the backend service.
- For the frontend, Railway will detect the Dockerfile in `app/` and serve on port 80.
- Railway provides `DATABASE_URL` as `postgres://...` — the backend auto-converts to `postgresql+psycopg2://`.
- Railway assigns a dynamic `PORT` — the start command binds to `${PORT:-8000}`.
