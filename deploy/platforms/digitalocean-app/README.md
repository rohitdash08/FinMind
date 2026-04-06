# Deploy FinMind to DigitalOcean App Platform

## One-Click Deploy
1. Fork this repository
2. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
3. Click "Create App" and connect your GitHub repo
4. Import `deploy/platforms/digitalocean-app/app.yaml` as the app spec

## CLI Deploy
```bash
doctl apps create --spec deploy/platforms/digitalocean-app/app.yaml
```
