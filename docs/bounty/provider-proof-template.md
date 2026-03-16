# Provider proof template

Use this table when filling a hosted deployment proof pack.

| Platform | Deploy command | Validate command | Frontend URL | Health URL | Screenshot | Smoke log | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Render | Blueprint via `render.yaml` | `./deploy/render/validate.sh --frontend-url https://finmind-frontend-sexs.onrender.com --api-url https://finmind-backend-ht43.onrender.com` | `https://finmind-frontend-sexs.onrender.com` | `https://finmind-backend-ht43.onrender.com/health/ready` | `docs/bounty/provider-proofs/render/render-2026-03-16-63ab7de.png` | `docs/bounty/provider-proofs/render/smoke.log` | UI log: `docs/bounty/provider-proofs/render/ui.log`; metadata: `docs/bounty/provider-proofs/render/metadata.txt`; deployed commit `63ab7de`; hosted proof video: `docs/demo/render-one-click-deploy-proof.mp4` |
| DigitalOcean App Platform | `./deploy/digitalocean/app-platform/deploy.sh --spec deploy/digitalocean/app-platform/app.yaml` | `./deploy/digitalocean/app-platform/validate.sh --frontend-url <url> --api-url <url>` | — | — | — | — | — |
| DigitalOcean Droplet | `AUTO_START=1 ./deploy/digitalocean/droplet/setup.sh` | `AUTO_START=1 AUTO_VALIDATE=1 ./deploy/digitalocean/droplet/setup.sh` | — | — | — | — | — |
| AWS ECS Fargate | `./deploy/aws/deploy.sh` | `./deploy/aws/validate.sh --frontend-url <url> --api-url <url>` | — | — | — | — | — |
| GCP Cloud Run | `./deploy/gcp/deploy.sh` | `./deploy/gcp/validate.sh --frontend-url <url> --api-url <url>` | — | — | — | — | — |
| Azure Container Apps | `./deploy/azure/deploy.sh` | `./deploy/azure/validate.sh --frontend-url <url> --api-url <url>` | — | — | — | — | — |
