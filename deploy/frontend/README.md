# Frontend Deployment

The FinMind frontend can be deployed to various static hosting providers.

## Vercel (Recommended)

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/rohitdash08/FinMind&root-directory=app)

### Manual Deploy
```bash
cd app
npm i -g vercel
vercel
```

### Environment Variables
Set in Vercel Dashboard:
- `VITE_API_URL`: Your backend API URL

## Netlify

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/rohitdash08/FinMind)

### Manual Deploy
```bash
cd app
npm i -g netlify-cli
netlify deploy --prod
```

### Configuration
The `netlify.toml` in `deploy/netlify/` handles:
- Build commands
- SPA redirects
- Security headers
- Environment-specific API URLs

## Cloudflare Pages

```bash
cd app
npm run build
npx wrangler pages deploy dist --project-name finmind-frontend
```

## Firebase Hosting

```bash
cd app
npm run build
firebase init hosting
firebase deploy
```

## GitHub Pages

Add to `.github/workflows/deploy-frontend.yml`:
```yaml
name: Deploy Frontend
on:
  push:
    branches: [main]
    paths: ['app/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: cd app && npm ci && npm run build
        env:
          VITE_API_URL: ${{ vars.VITE_API_URL }}
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./app/dist
```

## Self-Hosted (Nginx/Docker)

Use the `app/Dockerfile`:
```bash
cd app
docker build -t finmind-frontend .
docker run -p 80:80 finmind-frontend
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `VITE_API_URL` | Backend API URL | ✅ |
