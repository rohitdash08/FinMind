# Resilient Background Job Retry & Monitoring

> Implements [Issue #130](https://github.com/rohitdash08/FinMind/issues/130)

## Overview

FinMind's reminder dispatch now supports **automatic retries with exponential backoff** and a **job-run audit log** for monitoring.

Previously, `POST /reminders/run` would mark a reminder as `sent=True` regardless of whether the actual delivery (email/WhatsApp) succeeded. Failed deliveries were silently dropped.

## What Changed

### New Reminder fields

| Field | Type | Description |
|---|---|---|
| `retry_count` | integer | How many delivery attempts have been made |
| `max_retries` | integer | Maximum attempts before giving up (default: 3) |
| `next_retry_at` | datetime | When the next attempt should be made |
| `last_error` | string | Error message from the last failed attempt |
| `failed_permanently` | boolean | True when `retry_count >= max_retries` |

### Exponential Backoff

After each failure the next retry is scheduled at `2^retry_count` minutes:

| Attempt | Wait before retry |
|---|---|
| 1st failure | 2 minutes |
| 2nd failure | 4 minutes |
| 3rd failure | 8 minutes (→ `failed_permanently=True` with default `max_retries=3`) |

Maximum backoff is capped at **60 minutes**.

### `JobRun` audit table

Every call to `POST /reminders/run` creates a `job_runs` record:

```json
{
  "id": 1,
  "started_at": "2026-03-13T22:00:00",
  "finished_at": "2026-03-13T22:00:01",
  "status": "success",
  "processed": 5,
  "succeeded": 4,
  "errors": 1,
  "retried": 0
}
```

Status values: `success`, `partial` (some errors), `failed` (all errored), `running` (in-progress).

## API

### `POST /reminders/run`

Now returns a stats object instead of just `{ "processed": N }`:

```json
{
  "processed": 5,
  "succeeded": 4,
  "errors": 1,
  "retried": 1,
  "permanently_failed": 0
}
```

### `GET /reminders/job-runs`

Returns recent job run records (default: last 20, max 100 via `?limit=N`).

Requires JWT authentication.

## Database Migration

Run `packages/backend/app/db/migrations/002_resilient_job_retry.sql` against your PostgreSQL database:

```bash
psql $DATABASE_URL -f packages/backend/app/db/migrations/002_resilient_job_retry.sql
```

This adds the new columns to `reminders` and creates the `job_runs` table. All changes are `IF NOT EXISTS` safe for existing deployments.

## Architecture

```
POST /reminders/run
        │
        ▼
 job_runner.run_due_reminders(user_id)
        │
        ├─ query: sent=False, failed_permanently=False,
        │         next_retry_at IS NULL OR <= now,
        │         send_at <= now + 1min
        │
        ├─ for each reminder:
        │    ├─ send_reminder(r)
        │    │    ├─ OK  → sent=True, last_error=None
        │    │    └─ FAIL → retry_count++, last_error=...,
        │    │               next_retry_at = now + 2^n min
        │    │               if retry_count >= max_retries:
        │    │                   failed_permanently=True
        │    └─ track Prometheus event
        │
        └─ write JobRun record (status, processed, succeeded, errors)
```
