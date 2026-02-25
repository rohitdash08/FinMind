# FinMind — 部署指南

FinMind 支持多种部署方式，从本地开发到生产级云平台。选择最适合你的方案。

## 目录

- [本地开发 (Docker Compose)](#本地开发-docker-compose)
- [本地 K8s (Tilt)](#本地-k8s-tilt)
- [Railway](#railway)
- [Heroku](#heroku)
- [Render](#render)
- [Fly.io](#flyio)
- [DigitalOcean App Platform](#digitalocean-app-platform)
- [DigitalOcean Droplet](#digitalocean-droplet)
- [AWS ECS Fargate](#aws-ecs-fargate)
- [AWS App Runner](#aws-app-runner)
- [AWS CloudFormation](#aws-cloudformation)
- [GCP Cloud Run](#gcp-cloud-run)
- [Azure Container Apps](#azure-container-apps)
- [Netlify (前端)](#netlify-前端)
- [Vercel (前端)](#vercel-前端)

---

## 架构概览

```
┌─────────────┐     ┌─────────────┐
│   Frontend   │────▶│   Backend    │
│  (React/Vite)│     │  (Flask)     │
│   Port 80    │     │  Port 8000   │
└─────────────┘     └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │              │
              ┌─────▼─────┐ ┌─────▼─────┐
              │ PostgreSQL │ │   Redis    │
              │    16      │ │     7      │
              └───────────┘ └───────────┘
```

---

## 本地开发 (Docker Compose)

```bash
cp .env.example .env
# 编辑 .env 填入 API keys
docker compose up -d
```

| 服务 | 地址 |
|------|------|
| Backend | http://localhost:8000 |
| Frontend | http://localhost:5173 |
| Nginx | http://localhost:8080 |
| Grafana | http://localhost:3000 |

---

## 本地 K8s (Tilt)

前提：安装 [Tilt](https://docs.tilt.dev/install.html) + 本地 K8s 集群 (minikube/kind/Docker Desktop)

```bash
# 1. 创建命名空间和密钥
kubectl apply -f deploy/k8s/namespace.yaml
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
# 编辑 secrets.yaml 填入真实值
kubectl apply -f deploy/k8s/secrets.yaml

# 2. 启动 Tilt
tilt up
```

Tilt Dashboard: http://localhost:10350

---

## Railway

```bash
# 安装 Railway CLI: https://docs.railway.app/develop/cli
railway login
railway init

# 添加 PostgreSQL 和 Redis 插件
railway add --plugin postgresql
railway add --plugin redis

# 设置环境变量
railway variables set JWT_SECRET=$(openssl rand -hex 32)

# 部署
railway up
```

配置文件: `deploy/railway/railway.toml`

---

## Heroku

```bash
# 安装 Heroku CLI
heroku create finmind-app
heroku stack:set container

# 添加数据库
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# 设置密钥
heroku config:set JWT_SECRET=$(openssl rand -hex 32)
heroku config:set GEMINI_API_KEY=your-key

# 部署
cp deploy/heroku/heroku.yml .
git push heroku main
```

Review Apps: 在 Heroku Pipeline 中启用，使用 `deploy/heroku/app.json` 配置。

---

## Render

1. Fork 仓库到你的 GitHub
2. 登录 [Render Dashboard](https://dashboard.render.com)
3. New → Blueprint → 选择仓库
4. Render 自动检测 `deploy/render/render.yaml`
5. 填入环境变量 → Deploy

或使用 CLI:
```bash
render blueprint launch --file deploy/render/render.yaml
```

---

## Fly.io

```bash
# 安装 flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# 部署后端
cd packages/backend
fly launch --name finmind-backend --no-deploy
fly secrets set JWT_SECRET=$(openssl rand -hex 32)
fly secrets set DATABASE_URL="postgres://..."
fly secrets set REDIS_URL="redis://..."
fly deploy --config ../../deploy/fly/fly.toml

# 部署前端
cd ../../app
fly launch --name finmind-frontend --no-deploy
fly deploy --config ../deploy/fly/fly-frontend.toml
```

> 💡 Fly.io 提供免费的 PostgreSQL (fly postgres create) 和 Upstash Redis (fly redis create)

---

## DigitalOcean App Platform

```bash
# 安装 doctl: https://docs.digitalocean.com/reference/doctl/
doctl auth init
doctl apps create --spec deploy/digitalocean/.do/app.yaml
```

或在 DO 控制台 → Apps → Create App → From Spec，上传 `deploy/digitalocean/.do/app.yaml`。

---

## DigitalOcean Droplet

一键部署到 Ubuntu Droplet（最低 2 vCPU / 2 GB RAM）：

```bash
# SSH 到 Droplet 后执行
curl -sSL https://raw.githubusercontent.com/your-org/FinMind/main/deploy/digitalocean/scripts/droplet-setup.sh | bash

# 或带自定义域名和 SSL
FINMIND_DOMAIN=finmind.example.com CERTBOT_EMAIL=you@example.com bash droplet-setup.sh
```

脚本自动完成：安装 Docker、配置防火墙、克隆代码、生成安全密钥、启动服务、配置 systemd 开机自启。

---

## AWS ECS Fargate

```bash
# 1. 构建并推送镜像到 ECR
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker build -t finmind-backend packages/backend/
docker tag finmind-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest

# 2. 创建 Secrets Manager 密钥
aws secretsmanager create-secret --name finmind/jwt-secret --secret-string "$(openssl rand -hex 32)"

# 3. 注册任务定义
aws ecs register-task-definition --cli-input-json file://deploy/aws/ecs-task-definition.json

# 4. 创建服务
aws ecs create-service --cluster finmind --service-name finmind --task-definition finmind --desired-count 1 --launch-type FARGATE
```

配置文件: `deploy/aws/ecs-task-definition.json`

---

## AWS App Runner

```bash
# 推送镜像到 ECR 后
aws apprunner create-service \
  --service-name finmind-backend \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": { "Port": "8000" }
    }
  }'
```

配置参考: `deploy/aws/apprunner.yaml`

---

## AWS CloudFormation

一键部署完整基础设施（ECS + RDS + ElastiCache + ALB）：

```bash
aws cloudformation deploy \
  --template-file deploy/aws/cloudformation.yaml \
  --stack-name finmind \
  --parameter-overrides \
    VpcId=vpc-xxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    BackendImage=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-backend:latest \
    FrontendImage=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/finmind-frontend:latest \
    JwtSecret=$(openssl rand -hex 32) \
    DBPassword=$(openssl rand -hex 16) \
  --capabilities CAPABILITY_IAM
```

---

## GCP Cloud Run

```bash
# 1. 启用 API
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com

# 2. 创建 Artifact Registry 仓库
gcloud artifacts repositories create finmind --repository-format=docker --location=us-central1

# 3. 创建 Secrets
echo -n "$(openssl rand -hex 32)" | gcloud secrets create finmind-jwt-secret --data-file=-
echo -n "postgresql://..." | gcloud secrets create finmind-database-url --data-file=-
echo -n "redis://..." | gcloud secrets create finmind-redis-url --data-file=-

# 4. 构建并部署
gcloud builds submit --config deploy/gcp/cloudbuild.yaml .

# 或直接部署 service.yaml
gcloud run services replace deploy/gcp/service.yaml --region us-central1
```

---

## Azure Container Apps

```bash
# 1. 创建资源组和环境
az group create --name finmind-rg --location eastus
az containerapp env create --name finmind-env --resource-group finmind-rg --location eastus

# 2. 使用 Bicep 模板部署
az deployment group create \
  --resource-group finmind-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    backendImage='ghcr.io/your-org/finmind-backend:latest' \
    frontendImage='ghcr.io/your-org/finmind-frontend:latest' \
    jwtSecret='YOUR_SECRET' \
    databaseUrl='postgresql://...' \
    redisUrl='redis://...'

# 或使用 Docker Compose 兼容方式
az containerapp compose create \
  --resource-group finmind-rg \
  --environment finmind-env \
  --compose-file-path deploy/azure/azure-deploy.yaml
```

---

## Netlify (前端)

```bash
# 安装 Netlify CLI
npm i -g netlify-cli

# 部署
cd app
netlify deploy --prod

# 或连接 Git 仓库自动部署
netlify init
```

> ⚠️ 设置环境变量 `VITE_API_URL` 指向你的后端地址

配置文件: `deploy/netlify/netlify.toml`

---

## Vercel (前端)

```bash
# 安装 Vercel CLI
npm i -g vercel

# 部署
cd app
vercel --prod

# 或连接 Git 仓库
vercel link
```

> ⚠️ 在 Vercel 项目设置中配置 `VITE_API_URL` 环境变量
> ⚠️ 修改 `deploy/vercel/vercel.json` 中的 API 代理地址

配置文件: `deploy/vercel/vercel.json`

---

## 环境变量参考

所有平台都需要以下环境变量：

| 变量 | 必需 | 说明 |
|------|------|------|
| `DATABASE_URL` | ✅ | PostgreSQL 连接字符串 |
| `REDIS_URL` | ✅ | Redis 连接字符串 |
| `JWT_SECRET` | ✅ | JWT 签名密钥（至少 32 字符） |
| `GEMINI_API_KEY` | ❌ | Google Gemini API 密钥 |
| `GEMINI_MODEL` | ❌ | Gemini 模型名（默认 gemini-1.5-flash） |
| `LOG_LEVEL` | ❌ | 日志级别（默认 INFO） |
| `VITE_API_URL` | ✅* | 后端 API 地址（前端构建时需要） |

---

## 数据库迁移

所有部署方式中，后端启动时会自动执行：
```bash
python -m flask --app wsgi:app init-db
```

如需手动执行，进入后端容器运行此命令即可。
