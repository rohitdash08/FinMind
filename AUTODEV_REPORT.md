# AUTODEV Report

## Issue
- #124: Login anomaly detection & suspicious activity alerts
- URL: https://github.com/rohitdash08/FinMind/issues/124

## Changed Files
- `packages/backend/app/routes/auth.py`
  - Added login anomaly detection for:
    - `NEW_IP_ADDRESS`
    - `MULTIPLE_FAILED_ATTEMPTS`
  - Added `suspicious_activity_alert` payload on `/auth/login` responses.
  - Added `/auth/security-alerts` endpoint for authenticated users.
  - Added Redis-backed storage for known IPs, failed-attempt windows, and security alerts with in-process fallback when Redis is unavailable.
  - Hardened refresh token storage/revocation with Redis fallback so auth flows continue in local test environments without Redis.
- `packages/backend/app/__init__.py`
  - Added auth runtime-state reset at app initialization to avoid cross-instance memory fallback leakage.
- `packages/backend/app/openapi.yaml`
  - Documented login suspicious alert response shape.
  - Added `/auth/security-alerts` API documentation.
  - Added `SuspiciousActivityAlert` and `SecurityAlert` schemas.
- `packages/backend/tests/test_auth.py`
  - Added/validated regression tests for suspicious login detection:
    - new IP login alerting
    - multiple failed attempt alerting
- `README.md`
  - Updated auth endpoint notes and Redis key policy for security alerts.

## Test Commands
1. `PYTHONPATH=packages/backend pytest -q packages/backend/tests/test_auth.py`
2. `PYTHONPATH=packages/backend flake8 packages/backend/app/routes/auth.py packages/backend/app/__init__.py packages/backend/tests/test_auth.py`
3. `PYTHONPATH=packages/backend pytest -q packages/backend/tests`

## Results
- Command 1: **PASS** (`5 passed`)
- Command 2: **PASS** (no lint errors)
- Command 3: **FAIL** (`13 failed, 11 passed`) due to environment-level Redis unavailability (`redis:6379`) in unrelated cache paths (`bills/expenses/dashboard/reminders/observability`), not from auth anomaly changes.

## Risks / Follow-ups
- In-process fallback state is process-local; in multi-worker deployments, Redis should remain available for consistent cross-worker behavior.
- Without Redis, alert/history persistence is not durable across process restarts.
- Full backend suite in this workspace requires reachable Redis for non-auth cache invalidation code paths.
