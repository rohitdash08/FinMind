# 🚀 FinMind Deployment Quick Start

Get FinMind running in under 5 minutes!

## 📋 Choose Your Platform

### 🐳 Local Development (Fastest)

```bash
git clone https://github.com/rohitdash08/FinMind.git
cd FinMind
cp .env.example .env
docker-compose up --build
```

**Access:** Frontend at http://localhost:5173, Backend at http://localhost:8000

---

### ☁️ Cloud Platforms (Production)

#### Railway (Easiest)
```bash
railway login
railway init
railway add --plugin postgresql redis
railway up
```

#### Heroku
```bash
heroku create finmind-app
heroku addons:create heroku-postgresql:mini heroku-redis:mini
git push heroku main
```

#### Render
1. Fork the repo
2. Create new Blueprint on render.com
3. Upload `deploy/platforms/render.yaml`
4. Deploy!

#### Fly.io
```bash
fly launch --config deploy/platforms/fly.toml
fly postgres create --name finmind-db
fly postgres attach finmind-db
fly deploy
```

---

### ☸️ Kubernetes (Advanced)

```bash
# Using Helm
helm install finmind ./deploy/kubernetes/helm/finmind \
  --namespace finmind \
  --create-namespace \
  --set backend.secrets.JWT_SECRET='your-secret' \
  --set ingress.hosts[0].host='your-domain.com'

# Using Tilt (local dev)
tilt up
```

---

## ✅ Verify Deployment

Run the verification script:

```bash
./deploy/verify-deployment.sh <backend-url> <frontend-url>
```

Or manually check:

```bash
# Backend health
curl http://your-backend/health
# Expected: {"status":"ok"}

# Backend readiness
curl http://your-backend/ready
# Expected: {"status":"ready","database":"connected"}

# Frontend
curl http://your-frontend/
# Expected: HTML page
```

---

## 🔐 Required Environment Variables

Minimum required:
- `JWT_SECRET` - Random secret for JWT tokens
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string

Optional (for features):
- `OPENAI_API_KEY` or `GEMINI_API_KEY` - For AI insights
- `TWILIO_*` - For WhatsApp notifications
- `SMTP_URL` - For email notifications

---

## 📚 Full Documentation

- **Complete Guide:** [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md)
- **Kubernetes/Helm:** [deploy/kubernetes/helm/finmind/README.md](deploy/kubernetes/helm/finmind/README.md)
- **Platform Configs:** [deploy/platforms/](deploy/platforms/)

---

## 🆘 Troubleshooting

### Database connection failed?
Check `DATABASE_URL` format: `postgresql+psycopg2://user:pass@host:5432/dbname`

### Redis connection failed?
Check `REDIS_URL` format: `redis://host:6379/0`

### 500 Internal Server Error?
Check backend logs: `docker-compose logs backend` or `kubectl logs -n finmind -l app.kubernetes.io/component=backend`

---

## 💡 Tips

- **Local dev:** Use `docker-compose` for simplicity
- **Quick deploy:** Railway or Heroku for instant hosting
- **Production:** Kubernetes with Helm for scalability
- **Dev K8s:** Tilt for the best local K8s experience

---

**Need help?** Open an issue: https://github.com/rohitdash08/FinMind/issues

**For bounty:** Contact @geekster007 on Discord before submission!
