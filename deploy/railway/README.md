# Railway Deployment

## One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/finmind?referralCode=finmind)

## Manual Deployment

### 1. Create Project
```bash
railway login
railway init
```

### 2. Add Services

**PostgreSQL:**
```bash
railway add --service postgresql
```

**Redis:**
```bash
railway add --service redis
```

### 3. Configure Environment Variables
```bash
railway variables set JWT_SECRET=$(openssl rand -hex 32)
railway variables set GEMINI_API_KEY=your_key
railway variables set DATABASE_URL=${{Postgres.DATABASE_URL}}
railway variables set REDIS_URL=${{Redis.REDIS_URL}}
```

### 4. Deploy Backend
```bash
cd packages/backend
railway up
```

### 5. Deploy Frontend
Deploy the `app/` folder to Vercel or Netlify with:
- `VITE_API_URL` pointing to your Railway backend URL

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | ✅ |
| `REDIS_URL` | Redis connection string | ✅ |
| `JWT_SECRET` | JWT signing secret | ✅ |
| `GEMINI_API_KEY` | Google Gemini API key | ❌ |
| `OPENAI_API_KEY` | OpenAI API key (alternative) | ❌ |
| `LOG_LEVEL` | Logging level (INFO/DEBUG) | ❌ |

## Costs
- Railway Hobby: $5/month (includes $5 credit)
- PostgreSQL: Included in compute
- Redis: Included in compute

## Health Check
The backend exposes `/health` endpoint for Railway's health monitoring.
