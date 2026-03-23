# Render Deployment Guide
#
# Quick Start (one-click):
#   1. Click "New Blueprint" on https://dashboard.render.com
#   2. Connect your GitHub repo
#   3. Render auto-detects render.yaml and creates all services
#   4. Set GEMINI_API_KEY in the dashboard if using AI insights
#
# Manual Setup:
#   1. Fork the repo and connect to Render
#   2. Copy render.yaml to project root: cp deploy/paas/render/render.yaml .
#   3. Push to trigger deploy
#
# Notes:
#   - Free plan includes managed Postgres and Redis
#   - JWT_SECRET is auto-generated
#   - Frontend is deployed as a static site with SPA rewrites
#   - Backend uses Docker (the existing Dockerfile)
#   - Pull request previews are enabled for the frontend
