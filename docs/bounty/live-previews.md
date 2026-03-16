# Live previews

Render is the main hosted proof attached to this submission.

| Platform | Deploy command | Frontend URL | API URL | Health URL | Notes |
| --- | --- | --- | --- | --- | --- |
| Render | Branch-specific Blueprint via `render.yaml` | `https://finmind-frontend-sexs.onrender.com` | `https://finmind-backend-ht43.onrender.com` | `https://finmind-backend-ht43.onrender.com/health/ready` | Main proof. Rechecked on deployed commit `63ab7de`. Proof pack lives in `docs/bounty/provider-proofs/render/`. Free-tier cold starts may add a short delay after idle. |
| DigitalOcean App Platform | `./deploy/digitalocean/app-platform/deploy.sh --spec deploy/digitalocean/app-platform/app.yaml` | — | — | — | `PRE_DEPLOY` migration job closes init-db. |
| AWS ECS Fargate | `./deploy/aws/deploy.sh` | — | — | — | Full-stack image behind ALB. |
| GCP Cloud Run | `./deploy/gcp/deploy.sh` | — | — | — | Full-stack image served same-origin. |
| Azure Container Apps | `./deploy/azure/deploy.sh` | — | — | — | Full-stack image served same-origin. |
| Railway | Railway project from `railway.toml` | — | — | — | Uses pre-deploy `init-db` command. |
| Heroku | Heroku container app from `heroku.yml` + `app.json` | — | — | — | Uses release phase for `init-db`. |
| Fly.io | `./deploy/fly/deploy.sh` | — | — | — | Parameterized backend/frontend app names. |
