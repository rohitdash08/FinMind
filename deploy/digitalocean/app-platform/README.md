# Deploy FinMind on DigitalOcean App Platform

## One-Click Deploy

```bash
doctl apps create --spec deploy/digitalocean/app-platform/app-spec.yaml
```

## Manual Setup

1. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
2. Click **Create App** → **GitHub** → Select your FinMind fork
3. Import `deploy/digitalocean/app-platform/app-spec.yaml` as the app spec
4. Update `JWT_SECRET` with a secure value
5. Click **Create Resources**

## Verify

- Check the app dashboard for all components (API, Web, DB, Redis)
- Frontend URL and Backend URL are shown in the dashboard
- Test: `https://<app>.ondigitalocean.app/health`
