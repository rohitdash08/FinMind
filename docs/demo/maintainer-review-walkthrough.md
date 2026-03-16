# Maintainer review walkthrough

If you reopen `#308`, this is the shortest route through the attached evidence.

## 1. Render hosted proof

- Branch-specific Deploy to Render link: `https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fjuzigu40-ui%2FFinMind%2Ftree%2Fcodex%2Ffinmind-144-deploy-bounty`
- Frontend URL: `https://finmind-frontend-sexs.onrender.com`
- Health URL: `https://finmind-backend-ht43.onrender.com/health/ready`
- Proof pack: `docs/bounty/provider-proofs/render/`
- Hosted deploy proof video: `docs/demo/render-one-click-deploy-proof.mp4`
- Free-tier note: Render may cold-start after idle, so the first request can take longer than a warm check.

The current Render proof pack is tied to deployed commit `63ab7de`. The older `a622e03` and `f5667cd` packs remain under `docs/bounty/provider-proofs/render/archived/`.

## 2. Local review

Run:

```bash
./scripts/review-deploy.sh
```

That verifies:

- frontend reachability
- backend `/health`
- backend `/health/ready`
- database and Redis connectivity
- auth plus the core product modules
- Prometheus and Grafana health

## 3. K8s runtime

Current passing workflow run: `https://github.com/juzigu40-ui/FinMind/actions/runs/23119973032`

Run:

```bash
./scripts/review-k8s.sh
```

That path installs the Helm chart into kind, runs `helm test`, and then rechecks the frontend and backend through the same smoke path.

Tilt uses the same repo path:

```bash
tilt up
```

## 4. Provider proofs

Provider entry points live here:

- Render: `render.yaml`
- DigitalOcean App Platform: `.do/app.yaml`
- DigitalOcean Droplet: `deploy/digitalocean/droplet/setup.sh`
- AWS ECS Fargate: `deploy/aws/deploy.sh`
- GCP Cloud Run: `deploy/gcp/deploy.sh`
- Azure Container Apps: `deploy/azure/deploy.sh`

All hosted rechecks converge on:

```bash
./scripts/validate-public-deployment.sh \
  --frontend-url <url> \
  --api-base-url <url>
```

## 5. Supporting files

- Acceptance matrix: `docs/bounty/acceptance-matrix.md`
- Live previews worksheet: `docs/bounty/live-previews.md`
- Provider proof worksheet: `docs/bounty/provider-proof-template.md`
- Secondary product walkthrough: `docs/demo/finmind-deploy-demo.mp4`
