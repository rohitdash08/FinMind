# FinMind deployment guide

This branch is organized around the acceptance bar for `#144`: concrete deploy entry points, concrete validate entry points, closed init-db or migration paths, and a single public validation flow that can be reused across providers.

## Local review

Fastest full-stack review path:

```bash
./scripts/review-deploy.sh
```

What that path covers:

- production Compose startup
- PostgreSQL and Redis readiness
- auth plus the core modules used in the smoke flow
- Prometheus and Grafana health
- Helm lint and rendered manifest checks

Key local commands:

```bash
docker build -f Dockerfile.fullstack -t finmind-fullstack:test .
./scripts/review-deploy.sh
./scripts/record-demo-video.sh
```

The local demo recording can also export dated screenshots:

```bash
FINMIND_EXPORT_SCREENSHOTS=1 ./scripts/record-demo-video.sh
```

## K8s / Helm / Tilt

Runtime review entry:

```bash
./scripts/review-k8s.sh
```

That path:

- creates a kind cluster
- loads the branch-local backend and frontend images
- installs the Helm chart
- waits for rollout
- runs `helm test`
- runs the same smoke path against the port-forwarded services

Tilt entry:

```bash
tilt up
```

Tilt CI entry:

```bash
FINMIND_RUN_TILT_CI=1 ./scripts/review-k8s.sh
```

## Provider deploy / validate scripts

| Provider | Deploy entry | Validate entry | Notes |
| --- | --- | --- | --- |
| Render | Blueprint: `render.yaml` | `./deploy/render/validate.sh --frontend-url <url> --api-url <url>` | Free-tier compatible through `dockerCommand` plus `FINMIND_RUN_INIT_DB_ON_BOOT=1` |
| DigitalOcean App Platform | `./deploy/digitalocean/app-platform/deploy.sh --spec deploy/digitalocean/app-platform/app.yaml` | `./deploy/digitalocean/app-platform/validate.sh --frontend-url <url> --api-url <url>` | Uses `PRE_DEPLOY` migration job for `init-db` |
| DigitalOcean Droplet | `AUTO_START=1 ./deploy/digitalocean/droplet/setup.sh` | `AUTO_START=1 AUTO_VALIDATE=1 ./deploy/digitalocean/droplet/setup.sh` | Deploys the requested repo/ref/sha and does not auto-start on first checkout |
| AWS ECS Fargate | `./deploy/aws/deploy.sh` | `./deploy/aws/validate.sh --frontend-url <url> --api-url <url>` | Main AWS route for this submission |
| GCP Cloud Run | `./deploy/gcp/deploy.sh` | `./deploy/gcp/validate.sh --frontend-url <url> --api-url <url>` | Full-stack image served same-origin |
| Azure Container Apps | `./deploy/azure/deploy.sh` | `./deploy/azure/validate.sh --frontend-url <url> --api-url <url>` | Full-stack image served same-origin |
| Fly.io | `./deploy/fly/deploy.sh` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | Split backend/frontend route with parameterized app names |
| Railway | Railway config-as-code via `railway.toml` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `preDeployCommand` handles `init-db` |
| Heroku | Heroku container app via `heroku.yml` and `app.json` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | Release phase handles `init-db` |
| Netlify | `netlify deploy` with `netlify.toml` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | Frontend route against a chosen backend |
| Vercel | `vercel deploy` with `vercel.json` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | Frontend route against a chosen backend |

## Live proof collection

Public deployment smoke plus UI validation:

```bash
./scripts/validate-public-deployment.sh \
  --frontend-url https://your-preview.example \
  --api-base-url https://your-preview.example
```

Supporting files:

- Acceptance matrix: `docs/bounty/acceptance-matrix.md`
- Live previews: `docs/bounty/live-previews.md`
- Provider proof worksheet: `docs/bounty/provider-proof-template.md`
- Maintainer walkthrough: `docs/demo/maintainer-review-walkthrough.md`
