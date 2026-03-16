# Bounty Submission: Universal One-Click Deployment (Docker + K8s + Tilt) for FinMind

Discord coordination for `#144` is in place. If the maintainer wants the Discord record mirrored on GitHub, the screenshot note is prepared in `docs/bounty/discord-proof-comment.md`.

Current submission head: `f5667cd`

## Current checks

- CI: [23118157473](https://github.com/juzigu40-ui/FinMind/actions/runs/23118157473)
- Deploy Artifacts: [23118157478](https://github.com/juzigu40-ui/FinMind/actions/runs/23118157478)
- CodeQL: [23118157472](https://github.com/juzigu40-ui/FinMind/actions/runs/23118157472)

## Maintainer-requested free-platform one-click proof (Render)

- Branch-specific Deploy to Render link: `https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fjuzigu40-ui%2FFinMind%2Ftree%2Fcodex%2Ffinmind-144-deploy-bounty`
- Deployed commit: `f5667cd`
- Frontend URL: `https://finmind-frontend-sexs.onrender.com`
- API URL: `https://finmind-backend-ht43.onrender.com`
- Health URL: `https://finmind-backend-ht43.onrender.com/health/ready`
- Smoke log: [docs/bounty/provider-proofs/render/smoke.log](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/provider-proofs/render/smoke.log)
- UI validation log: [docs/bounty/provider-proofs/render/ui.log](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/provider-proofs/render/ui.log)
- Screenshot: [docs/bounty/provider-proofs/render/render-2026-03-16-f5667cd.png](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/provider-proofs/render/render-2026-03-16-f5667cd.png)
- Metadata: [docs/bounty/provider-proofs/render/metadata.txt](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/provider-proofs/render/metadata.txt)
- Hosted deploy proof video: [docs/demo/render-one-click-deploy-proof.mp4](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/demo/render-one-click-deploy-proof.mp4)
- Free-tier note: Render may cold-start after idle, so the first request can take longer than a warm check.

## Acceptance entry page

| Platform | Deploy command | Validate command | Proof status | Live URL |
| --- | --- | --- | --- | --- |
| Production Compose | `./scripts/review-deploy.sh` | `./scripts/review-deploy.sh` | `CI-validated` | Local only |
| Kubernetes / Helm | `./scripts/review-k8s.sh` | `helm test finmind -n finmind --logs` | `CI-validated` | Local only |
| Tilt | `tilt up` | `tilt ci --timeout 10m` | `CI-validated` | Local only |
| Render | Blueprint: `render.yaml` | `./deploy/render/validate.sh --frontend-url https://finmind-frontend-sexs.onrender.com --api-url https://finmind-backend-ht43.onrender.com` | `Provider-validated` | `https://finmind-frontend-sexs.onrender.com` |
| DigitalOcean App Platform | `./deploy/digitalocean/app-platform/deploy.sh --spec deploy/digitalocean/app-platform/app.yaml` | `./deploy/digitalocean/app-platform/validate.sh --frontend-url <url> --api-url <url>` | `Repo-ready` | — |
| DigitalOcean Droplet | `AUTO_START=1 ./deploy/digitalocean/droplet/setup.sh` | `AUTO_START=1 AUTO_VALIDATE=1 ./deploy/digitalocean/droplet/setup.sh` | `Repo-ready` | — |
| AWS ECS Fargate | `./deploy/aws/deploy.sh` | `./deploy/aws/validate.sh --frontend-url <url> --api-url <url>` | `Repo-ready` | — |
| GCP Cloud Run | `./deploy/gcp/deploy.sh` | `./deploy/gcp/validate.sh --frontend-url <url> --api-url <url>` | `Repo-ready` | — |
| Azure Container Apps | `./deploy/azure/deploy.sh` | `./deploy/azure/validate.sh --frontend-url <url> --api-url <url>` | `Repo-ready` | — |

## Review files

- Acceptance matrix: [docs/bounty/acceptance-matrix.md](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/acceptance-matrix.md)
- Live previews worksheet: [docs/bounty/live-previews.md](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/live-previews.md)
- Provider proof worksheet: [docs/bounty/provider-proof-template.md](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/bounty/provider-proof-template.md)
- Maintainer walkthrough: [docs/demo/maintainer-review-walkthrough.md](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/demo/maintainer-review-walkthrough.md)
- Secondary product walkthrough: [docs/demo/finmind-deploy-demo.mp4](https://github.com/juzigu40-ui/FinMind/blob/codex/finmind-144-deploy-bounty/docs/demo/finmind-deploy-demo.mp4)

## What changed in the submission path

- Hosted validation now converges on `./scripts/validate-public-deployment.sh`, so the same smoke and UI path can be reused across public deployments.
- The hosted proof logs now carry provider, deployed commit, UTC timestamp, URLs, readiness JSON, and module/path summaries instead of a one-line pass.
- Render is now the primary hosted proof on the first screen, with a dedicated proof video focused on the free-platform one-click path rather than only the product walkthrough.
- The older `a622e03` Render artifacts were archived under `docs/bounty/provider-proofs/render/archived/a622e03/` so they do not remain the primary proof set.
