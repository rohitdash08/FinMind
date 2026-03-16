# FinMind acceptance matrix

Status labels used below:

- `Maintainer-run`: the branch contains a deploy path and a validate path, but no live provider run is attached here.
- `CI-validated`: the branch path is exercised in CI on this submission.
- `Provider-validated`: a real provider deployment was brought up and rechecked with the branch validate path.

| Platform | Deploy command | Validate command | Proof status | Live URL |
| --- | --- | --- | --- | --- |
| Production Compose | `./scripts/review-deploy.sh` | `./scripts/review-deploy.sh` | `CI-validated` | Local only |
| Kubernetes / Helm | `./scripts/review-k8s.sh` | `helm test finmind -n finmind --logs` | `CI-validated` | Local only |
| Tilt | `tilt up` | `tilt ci --timeout 10m` | `CI-validated` | Local only |
| Render | Blueprint: `render.yaml` | `./deploy/render/validate.sh --frontend-url https://finmind-frontend-sexs.onrender.com --api-url https://finmind-backend-ht43.onrender.com` | `Provider-validated` | `https://finmind-frontend-sexs.onrender.com` |
| DigitalOcean App Platform | `./deploy/digitalocean/app-platform/deploy.sh --spec deploy/digitalocean/app-platform/app.yaml` | `./deploy/digitalocean/app-platform/validate.sh --frontend-url <url> --api-url <url>` | `Maintainer-run` | — |
| DigitalOcean Droplet | `AUTO_START=1 ./deploy/digitalocean/droplet/setup.sh` | `AUTO_START=1 AUTO_VALIDATE=1 ./deploy/digitalocean/droplet/setup.sh` | `Maintainer-run` | — |
| Railway | Railway config-as-code via `railway.toml` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `Maintainer-run` | — |
| Heroku | `heroku stack:set container` with `heroku.yml` + `app.json` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `Maintainer-run` | — |
| Fly.io | `./deploy/fly/deploy.sh` | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `Maintainer-run` | — |
| AWS ECS Fargate | `./deploy/aws/deploy.sh` | `./deploy/aws/validate.sh --frontend-url <url> --api-url <url>` | `Maintainer-run` | — |
| GCP Cloud Run | `./deploy/gcp/deploy.sh` | `./deploy/gcp/validate.sh --frontend-url <url> --api-url <url>` | `Maintainer-run` | — |
| Azure Container Apps | `./deploy/azure/deploy.sh` | `./deploy/azure/validate.sh --frontend-url <url> --api-url <url>` | `Maintainer-run` | — |
| Netlify | `netlify deploy` with `netlify.toml` against a chosen backend | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `Maintainer-run` | — |
| Vercel | `vercel deploy` with `vercel.json` against a chosen backend | `./scripts/validate-public-deployment.sh --frontend-url <url> --api-base-url <url>` | `Maintainer-run` | — |

## AWS optional appendix

`deploy/aws/apprunner.yaml` remains in the branch as an optional appendix. It is not part of the main AWS claim for this submission; the primary AWS route is ECS Fargate via `deploy/aws/cloudformation.yaml` and `deploy/aws/deploy.sh`.
