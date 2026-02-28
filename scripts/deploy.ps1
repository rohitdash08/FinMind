# FinMind Universal One-Click Deployment Script (Windows)
# Usage: .\scripts\deploy.ps1 [Platform] [Environment]
#
# Platforms: docker, docker-prod, kubernetes, helm, tilt, fly, railway, render, heroku
# Environment: dev, staging, production (default: dev)

param(
    [Parameter(Position=0)]
    [ValidateSet("docker", "docker-prod", "kubernetes", "helm", "tilt", "fly", "railway", "heroku", "render", "help")]
    [string]$Platform = "docker",
    
    [Parameter(Position=1)]
    [ValidateSet("dev", "staging", "production")]
    [string]$Environment = "dev"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Write-Log { param([string]$Message) Write-Host "[FinMind] $Message" -ForegroundColor Blue }
function Write-Success { param([string]$Message) Write-Host "[✓] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[!] $Message" -ForegroundColor Yellow }
function Write-Error { param([string]$Message) Write-Host "[✗] $Message" -ForegroundColor Red; exit 1 }

function Test-Command { param([string]$Command) return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue) }

function Test-Prerequisites {
    Write-Log "Checking prerequisites..."
    
    switch ($Platform) {
        { $_ -in "docker", "docker-prod" } {
            if (-not (Test-Command "docker")) { Write-Error "Docker is required" }
        }
        { $_ -in "kubernetes", "helm" } {
            if (-not (Test-Command "kubectl")) { Write-Error "kubectl is required" }
            if (-not (Test-Command "helm")) { Write-Error "Helm is required" }
        }
        "tilt" {
            if (-not (Test-Command "tilt")) { Write-Error "Tilt is required (install from https://tilt.dev)" }
            if (-not (Test-Command "kubectl")) { Write-Error "kubectl is required" }
        }
        "fly" {
            if (-not (Test-Command "flyctl")) { Write-Error "flyctl is required" }
        }
        "railway" {
            if (-not (Test-Command "railway")) { Write-Error "Railway CLI is required (npm install -g @railway/cli)" }
        }
    }
    
    Write-Success "Prerequisites check passed"
}

function Initialize-Environment {
    Write-Log "Setting up environment..."
    
    $envFile = Join-Path $ProjectRoot ".env"
    $envExample = Join-Path $ProjectRoot ".env.example"
    
    if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envFile
        Write-Warn "Created .env from .env.example - please update with your secrets"
    }
    
    # Generate JWT secret if not set
    if (Test-Path $envFile) {
        $content = Get-Content $envFile -Raw
        if ($content -notmatch "JWT_SECRET=.") {
            $bytes = New-Object byte[] 32
            [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $jwtSecret = [Convert]::ToBase64String($bytes)
            Add-Content $envFile "JWT_SECRET=$jwtSecret"
            Write-Success "Generated JWT_SECRET"
        }
    }
}

function Deploy-Docker {
    Write-Log "Deploying with Docker Compose (development)..."
    Push-Location $ProjectRoot
    
    docker compose build
    docker compose up -d
    
    Pop-Location
    Write-Success "Docker Compose deployment complete!"
    Write-Host ""
    Write-Log "Services running:"
    Write-Host "  Frontend:   http://localhost:5173"
    Write-Host "  Backend:    http://localhost:8000"
    Write-Host "  Nginx:      http://localhost:8080"
    Write-Host "  Grafana:    http://localhost:3000"
    Write-Host ""
    Write-Log "View logs: docker compose logs -f"
    Write-Log "Stop: docker compose down"
}

function Deploy-DockerProd {
    Write-Log "Deploying with Docker Compose (production)..."
    Push-Location $ProjectRoot
    
    docker compose -f docker-compose.prod.yml build
    docker compose -f docker-compose.prod.yml up -d
    
    Pop-Location
    Write-Success "Production Docker Compose deployment complete!"
    Write-Host ""
    Write-Log "Services running:"
    Write-Host "  Backend: http://localhost:8000"
    Write-Host "  Nginx:   http://localhost:80"
}

function Deploy-Kubernetes {
    Write-Log "Deploying to Kubernetes..."
    Push-Location $ProjectRoot
    
    kubectl apply -f deploy/k8s/namespace.yaml
    
    $secretsFile = Join-Path $ProjectRoot "deploy/k8s/secrets.yaml"
    if (-not (Test-Path $secretsFile)) {
        Copy-Item (Join-Path $ProjectRoot "deploy/k8s/secrets.example.yaml") $secretsFile
        Write-Warn "Created secrets.yaml from example - please update with your secrets"
        Pop-Location
        exit 1
    }
    
    kubectl apply -f deploy/k8s/secrets.yaml
    kubectl apply -f deploy/k8s/app-stack.yaml
    
    Write-Log "Waiting for pods..."
    kubectl wait --namespace finmind --for=condition=ready pod -l app=backend --timeout=300s
    
    Pop-Location
    Write-Success "Kubernetes deployment complete!"
    Write-Host ""
    Write-Log "Check status: kubectl get pods -n finmind"
}

function Deploy-Helm {
    Write-Log "Deploying with Helm..."
    Push-Location (Join-Path $ProjectRoot "deploy/helm/finmind")
    
    helm repo add bitnami https://charts.bitnami.com/bitnami 2>$null
    helm repo update
    helm dependency update
    
    # Generate secrets
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $jwtSecret = [Convert]::ToBase64String($bytes)
    
    $bytes16 = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes16)
    $pgPassword = [Convert]::ToBase64String($bytes16)
    
    helm upgrade --install finmind . `
        --namespace finmind --create-namespace `
        --set secrets.jwtSecret="$jwtSecret" `
        --set postgresql.auth.password="$pgPassword" `
        --wait --timeout 10m
    
    Pop-Location
    Write-Success "Helm deployment complete!"
    Write-Host ""
    Write-Log "Check status: helm status finmind -n finmind"
}

function Deploy-Tilt {
    Write-Log "Starting Tilt (local Kubernetes development)..."
    Push-Location $ProjectRoot
    
    $secretsFile = Join-Path $ProjectRoot "deploy/k8s/secrets.yaml"
    if (-not (Test-Path $secretsFile)) {
        Copy-Item (Join-Path $ProjectRoot "deploy/k8s/secrets.example.yaml") $secretsFile
        Write-Warn "Created secrets.yaml from example"
    }
    
    tilt up
    Pop-Location
}

function Deploy-Fly {
    Write-Log "Deploying to Fly.io..."
    Push-Location $ProjectRoot
    
    flyctl deploy --config deploy/fly/fly.toml --remote-only
    
    Pop-Location
    Write-Success "Fly.io deployment complete!"
    Write-Host ""
    Write-Log "App URL: https://finmind-api.fly.dev"
}

function Deploy-Railway {
    Write-Log "Deploying to Railway..."
    Push-Location $ProjectRoot
    
    railway up --detach
    
    Pop-Location
    Write-Success "Railway deployment initiated!"
}

function Show-Help {
    Write-Host @"
FinMind Universal Deployment Script (Windows)

Usage: .\scripts\deploy.ps1 [Platform] [Environment]

Platforms:
  docker       - Docker Compose (development, default)
  docker-prod  - Docker Compose (production)
  kubernetes   - Raw Kubernetes manifests
  helm         - Helm chart deployment
  tilt         - Tilt local K8s development
  fly          - Fly.io
  railway      - Railway
  heroku       - Heroku
  render       - Render (instructions)

Examples:
  .\scripts\deploy.ps1                    # Docker Compose dev
  .\scripts\deploy.ps1 docker-prod        # Docker Compose production
  .\scripts\deploy.ps1 helm production    # Helm to production K8s
  .\scripts\deploy.ps1 fly                # Deploy to Fly.io
"@
}

# Main
switch ($Platform) {
    "help" { Show-Help }
    "docker" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Docker
    }
    "docker-prod" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-DockerProd
    }
    "kubernetes" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Kubernetes
    }
    "helm" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Helm
    }
    "tilt" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Tilt
    }
    "fly" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Fly
    }
    "railway" {
        Test-Prerequisites
        Initialize-Environment
        Deploy-Railway
    }
    default {
        Write-Error "Unknown platform: $Platform. Use 'help' for usage."
    }
}
