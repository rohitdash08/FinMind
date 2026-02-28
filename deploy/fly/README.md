# Fly.io Deployment

## Quick Deploy

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Deploy from repo root
flyctl launch --config deploy/fly/fly.toml
```

## Step-by-Step

### 1. Create App
```bash
flyctl apps create finmind-api
```

### 2. Create PostgreSQL
```bash
flyctl postgres create --name finmind-db
flyctl postgres attach finmind-db --app finmind-api
```

### 3. Create Redis (Upstash)
```bash
flyctl redis create --name finmind-redis
```

### 4. Set Secrets
```bash
flyctl secrets set JWT_SECRET=$(openssl rand -hex 32)
flyctl secrets set GEMINI_API_KEY=your_key
flyctl secrets set REDIS_URL=your_upstash_url
```

### 5. Deploy
```bash
flyctl deploy --config deploy/fly/fly.toml
```

### 6. Scale (Optional)
```bash
# Add more machines
flyctl scale count 2

# Upgrade VM
flyctl scale vm shared-cpu-2x
```

## Frontend Deployment

Deploy `app/` to Fly.io as static site:

```bash
cd app
npm run build
flyctl launch --dockerfile ../deploy/fly/Dockerfile.frontend
```

Or use Vercel/Netlify for the frontend.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | Auto-attached by Postgres | ✅ |
| `REDIS_URL` | Upstash Redis URL | ✅ |
| `JWT_SECRET` | JWT signing secret | ✅ |
| `GEMINI_API_KEY` | AI API key | ❌ |

## Pricing

- Hobby: Free tier with 3 shared VMs
- PostgreSQL: Free 256MB
- Redis (Upstash): Free 10k commands/day

## Monitoring

```bash
flyctl logs -a finmind-api
flyctl status
flyctl dashboard
```
