# Railway Deployment

## Quick Start

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
   ```
   DATABASE_URL=<from Railway Postgres plugin>
   REDIS_URL=<from Railway Redis plugin>
   JWT_SECRET=<your-secret>
   ```

5. Deploy:
   ```bash
   railway up
   ```

## Notes

- Railway auto-detects Dockerfiles in each service root.
- The `railway.json` in this directory configures the backend service.
- For the frontend, Railway will detect the Dockerfile in `app/` and serve on port 80.
- Use Railway's built-in PostgreSQL and Redis plugins for managed databases.
