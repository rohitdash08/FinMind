# FinMind Makefile - One-command deployment and development
.PHONY: help dev prod build test lint clean deploy-docker deploy-helm deploy-tilt deploy-fly deploy-railway

# Default target
help:
	@echo "FinMind - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start development environment (Docker Compose)"
	@echo "  make prod         - Start production environment (Docker Compose)"
	@echo "  make tilt         - Start Tilt (local K8s development)"
	@echo "  make build        - Build Docker images"
	@echo "  make test         - Run all tests"
	@echo "  make lint         - Run linters"
	@echo "  make clean        - Stop and remove containers"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-helm  - Deploy to Kubernetes with Helm"
	@echo "  make deploy-fly   - Deploy to Fly.io"
	@echo "  make deploy-railway - Deploy to Railway"
	@echo ""
	@echo "Utilities:"
	@echo "  make logs         - View container logs"
	@echo "  make shell-backend  - Shell into backend container"
	@echo "  make db-migrate   - Run database migrations"

# ============== Development ==============

dev:
	@echo "Starting development environment..."
	cp -n .env.example .env 2>/dev/null || true
	docker compose up --build

prod:
	@echo "Starting production environment..."
	docker compose -f docker-compose.prod.yml up -d --build

tilt:
	@echo "Starting Tilt..."
	@test -f deploy/k8s/secrets.yaml || cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
	tilt up

build:
	@echo "Building Docker images..."
	docker compose build
	docker compose -f docker-compose.prod.yml build

test:
	@echo "Running tests..."
	docker compose exec backend pytest tests/ -v || docker compose run --rm backend pytest tests/ -v
	cd app && npm test

lint:
	@echo "Running linters..."
	docker compose exec backend black --check . || docker compose run --rm backend black --check .
	docker compose exec backend flake8 . || docker compose run --rm backend flake8 .
	cd app && npm run lint

clean:
	@echo "Cleaning up..."
	docker compose down -v --remove-orphans
	docker compose -f docker-compose.prod.yml down -v --remove-orphans 2>/dev/null || true

# ============== Deployment ==============

deploy-docker: prod
	@echo "Deployed with Docker Compose (production)"

deploy-helm:
	@echo "Deploying to Kubernetes with Helm..."
	./scripts/deploy.sh helm

deploy-fly:
	@echo "Deploying to Fly.io..."
	./scripts/deploy.sh fly

deploy-railway:
	@echo "Deploying to Railway..."
	./scripts/deploy.sh railway

deploy-k8s:
	@echo "Deploying to Kubernetes..."
	./scripts/deploy.sh kubernetes

# ============== Utilities ==============

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend-dev

shell-backend:
	docker compose exec backend sh

shell-frontend:
	docker compose exec frontend-dev sh

db-migrate:
	docker compose exec backend python -m flask --app wsgi:app init-db

# ============== Setup ==============

setup:
	@echo "Setting up FinMind..."
	cp -n .env.example .env || true
	@echo ""
	@echo "Please edit .env with your configuration, then run:"
	@echo "  make dev   - for development"
	@echo "  make prod  - for production"

# ============== CI/CD ==============

ci-test:
	@echo "Running CI tests..."
	cd packages/backend && pip install -r requirements.txt && pytest tests/ -v
	cd app && npm ci && npm test

ci-lint:
	@echo "Running CI linters..."
	cd packages/backend && black --check . && flake8 .
	cd app && npm run lint

ci-build:
	@echo "Building for CI..."
	docker build -t finmind-backend ./packages/backend
	docker build -t finmind-frontend ./app
