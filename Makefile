# FinMind — Makefile
# ──────────────────
# Common commands for development and deployment

.PHONY: help dev prod down logs test lint build push clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Development ───────────────────────────────────

dev: ## Start development environment (Docker Compose)
	cp -n .env.example .env 2>/dev/null || true
	docker compose up -d
	@echo "✅ Dev environment running"
	@echo "   Backend:  http://localhost:8000"
	@echo "   Frontend: http://localhost:5173"
	@echo "   Grafana:  http://localhost:3000"

tilt: ## Start Tilt local K8s development
	tilt up

prod: ## Start production environment
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

down: ## Stop all services
	docker compose down

logs: ## Tail all logs
	docker compose logs -f

logs-backend: ## Tail backend logs
	docker compose logs -f backend

# ── Testing ───────────────────────────────────────

test: ## Run all tests
	cd app && npm test -- --run
	cd packages/backend && python -m pytest

lint: ## Run linters
	cd app && npm run lint
	cd packages/backend && flake8 app/

# ── Docker ────────────────────────────────────────

build: ## Build Docker images
	docker build -t finmind-backend -f packages/backend/Dockerfile packages/backend/
	docker build -t finmind-frontend -f app/Dockerfile app/

push: build ## Build and push to GHCR
	docker tag finmind-backend ghcr.io/rohitdash08/finmind-backend:latest
	docker tag finmind-frontend ghcr.io/rohitdash08/finmind-frontend:latest
	docker push ghcr.io/rohitdash08/finmind-backend:latest
	docker push ghcr.io/rohitdash08/finmind-frontend:latest

# ── Kubernetes ────────────────────────────────────

helm-install: ## Install via Helm
	helm install finmind deploy/helm/finmind -n finmind --create-namespace

helm-upgrade: ## Upgrade via Helm
	helm upgrade finmind deploy/helm/finmind -n finmind

helm-uninstall: ## Uninstall Helm release
	helm uninstall finmind -n finmind

# ── Cleanup ───────────────────────────────────────

clean: ## Remove all containers, volumes, and images
	docker compose down -v --rmi all
	@echo "✅ Cleaned up"
