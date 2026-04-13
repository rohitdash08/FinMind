# Repo Playbook

## FinMind quick read
- Repo: rohitdash08/FinMind
- Main stack: Flask backend in `packages/backend`, React/Vite frontend in `app`
- CI gates: backend lint/tests/bandit, docker scan, frontend lint/tests/build
- Contribution model says fork-first, small focused PRs, owner review required

## Current low-risk target area
- Backend reminders are the best fit for a narrow, testable patch.
- Best practical shape is a backend-only behavior fix with API-level pytest coverage.
- Current cycle target: issue #123, keep failed reminder dispatch unsent and visible.
- Local reminder tests may need the fake Redis fixture in `tests/conftest.py`, so keep proof runnable without a live Redis daemon.

## Guardrails
- Keep the PR to one claim.
- Prefer API-level tests over internal unit-only tests.
- Update evidence first, then code, then checks.
- Avoid broad retry architecture unless the issue explicitly demands it.
