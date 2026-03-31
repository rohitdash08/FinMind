#!/bin/bash
# Atlas Environmental Sentry - Universal Deployer
echo "🚀 Initializing FinMind Universal One-Click Setup..."

if command -v tilt >/dev/null 2>&1; then
    echo "✅ Tilt detected. Launching Kubernetes-native developer experience..."
    tilt up
elif command -v docker-compose >/dev/null 2>&1; then
    echo "⚠️ Tilt/K8s not found. Falling back to enhanced Docker-Compose mode..."
    docker-compose up -d
else
    echo "❌ Error: Neither Tilt nor Docker-Compose detected. Please install Docker Desktop."
    exit 1
fi
