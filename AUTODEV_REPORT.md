# AUTODEV REPORT

## Issue
- #121: Smart digest with weekly financial summary
- URL: https://github.com/rohitdash08/FinMind/issues/121

## Changed Files
- `packages/backend/tests/test_digest.py`
  - Added TDD coverage for weekly digest endpoint: payload shape, week-over-week math, default current week behavior, invalid week validation, Gemini fallback.
- `packages/backend/app/services/digest.py`
  - Added weekly digest service with:
    - ISO week window calculation
    - Weekly totals (income/expenses/net)
    - Previous-week comparison and WoW percentage
    - Category and daily breakdowns
    - Transaction count
    - Heuristic insights
    - Optional Gemini-based insights with graceful fallback
- `packages/backend/app/routes/insights.py`
  - Added authenticated `GET /insights/weekly-digest` route.
  - Supports optional `year` and `week` query params.
  - Supports optional headers `X-Gemini-Api-Key` and `X-Insight-Persona`.
  - Returns `400` for invalid ISO week/year input.
- `packages/backend/app/openapi.yaml`
  - Documented `GET /insights/weekly-digest` endpoint.
- `README.md`
  - Added `/insights/weekly-digest` to the API endpoint list.

## Test Commands
1. `cd packages/backend && python -m pytest -q tests/test_digest.py`
2. `cd packages/backend && REDIS_URL=redis://localhost:6379/15 python -m pytest -q tests`
3. `cd packages/backend && python -m flake8 app/routes/insights.py app/services/digest.py tests/test_digest.py`

## Test Results
- Command 1: **PASS** (`5 passed`)
- Command 2: **PASS** (`27 passed`) after setting `REDIS_URL` to local Redis.
- Command 3: **PASS** (no lint errors)

## Risks / Notes
- The weekly digest endpoint currently computes data on demand (no cache layer); heavy historical usage may increase DB load.
- Category grouping uses category name and labels missing categories as `Uncategorized`.
- Gemini insight generation depends on upstream availability; endpoint gracefully falls back to heuristic insights with `warnings: ["gemini_unavailable"]`.
