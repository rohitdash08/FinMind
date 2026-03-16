# Deployment artifact map

| Target | Entry file(s) |
| --- | --- |
| Production Compose | `docker-compose.prod.yml` |
| Production Compose + observability | `docker-compose.prod.yml` with `FINMIND_COMPOSE_PROFILES=observability` |
| Kubernetes raw manifests | `deploy/k8s/` |
| Helm | `deploy/helm/finmind/` |
| Tilt | `Tiltfile` |
| Railway | `railway.toml` |
| Heroku | `heroku.yml`, `app.json` |
| Render | `render.yaml` |
| DigitalOcean App Platform | `.do/app.yaml` |
| DigitalOcean Droplet | `deploy/digitalocean/droplet/setup.sh` |
| Fly.io | `deploy/fly/` |
| AWS | `deploy/aws/` |
| GCP | `deploy/gcp/` |
| Azure | `deploy/azure/` |
| Netlify | `netlify.toml` |
| Vercel | `vercel.json` |

See `DEPLOY.md` for the runtime verification flow, the observability smoke path, and platform notes.
