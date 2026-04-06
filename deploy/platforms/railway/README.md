# Deploy FinMind to Railway

## One-Click Deploy
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/finmind)

## Manual Setup
1. Create a new project on [Railway](https://railway.app)
2. Add a PostgreSQL database service
3. Add a Redis service
4. Deploy the backend:
   ```bash
   railway link
   railway up -s backend
   ```
5. Deploy the frontend:
   ```bash
   railway up -s frontend
   ```
6. Set environment variables in Railway dashboard (see `.env.example`)

## Required Environment Variables
- `DATABASE_URL` - Auto-provided by Railway PostgreSQL plugin
- `REDIS_URL` - Auto-provided by Railway Redis plugin
- `JWT_SECRET` - Set manually
- `VITE_API_URL` - Set to your backend Railway URL
