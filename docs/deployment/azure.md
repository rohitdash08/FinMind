# azure Deployment Guide

See the main [Deployment README](./README.md) for quick start instructions.

Refer to platform-specific configs in the deploy directory.

## Prerequisites
- Account on the platform
- Platform CLI installed
- Docker images built (if applicable)
- Environment variables from .env.example

## Verification
1. Frontend loads in browser
2. GET /health returns 200
3. Register a user (DB connected)
4. Check Redis connectivity (sessions work)
5. Test core modules: expenses, bills, reminders, dashboard, insights
