# Resilient Background Job Retry & Monitoring

> Issue: [#130](https://github.com/rohitdash08/FinMind/issues/130)

## Overview

Replaces the manual, fire-and-forget `/reminders/run` endpoint with a production-grade background job system that processes reminders automatically with retry, dead-letter handling, and full observability.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  APScheduler (BackgroundScheduler)              │
│  ┌───────────────────────────────┐              │
│  │ process_due_reminders()       │ every 60s    │
│  │ - Recover stale "sending"     │              │
│  │ - Fetch due reminders         │              │
│  │ - Send with per-item commit   │              │
│  │ - Exponential backoff retry   │              │
│  │ - Dead-letter after max tries │              │
│  └───────────────┬───────────────┘              │
│                  │                              │
│  ┌───────────────▼───────────────┐              │
│  │ send_reminder(r)              │              │
│  │  ├─ email (SMTP)              │              │
│  │  └─ whatsapp (Twilio)         │              │
│  └───────────────────────────────┘              │
└─────────────────────────────────────────────────┘

Reminder Status Flow:
  pending ──► sending ──► sent ✓
                │
                ▼ (failure)
             failed ──► sending (retry) ──► sent ✓
                │
                ▼ (max retries exceeded)
              dead (dead-letter queue)
```

## What Changed

### Model Changes (`app/models.py`)

New columns on `Reminder`:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `status` | VARCHAR(20) | `"pending"` | Lifecycle state: pending/sending/sent/failed/dead |
| `retry_count` | INTEGER | `0` | Number of delivery attempts |
| `max_retries` | INTEGER | `3` | Maximum attempts before dead-letter |
| `last_error` | VARCHAR(500) | `NULL` | Most recent error message |
| `next_retry_at` | TIMESTAMP | `NULL` | When to retry a failed reminder |
| `started_at` | TIMESTAMP | `NULL` | When delivery was last attempted |
| `completed_at` | TIMESTAMP | `NULL` | When delivery succeeded or was dead-lettered |

### New Files

| File | Purpose |
|------|---------|
| `app/services/job_runner.py` | Core retry engine with `process_due_reminders()` |
| `app/scheduler.py` | APScheduler integration for automatic background processing |
| `app/routes/jobs.py` | Admin API for monitoring and management |
| `app/db/003_resilient_job_retry.sql` | SQL migration with partial indexes |
| `tests/test_job_runner.py` | 18 test cases |

## API Endpoints

### `GET /jobs/status`
Returns scheduler health and reminder pipeline statistics.

```json
{
  "scheduler": {
    "running": true,
    "next_run_time": "2026-03-14T10:01:00+00:00"
  },
  "stats": {
    "pending": 12,
    "sending": 1,
    "sent": 450,
    "failed": 2,
    "dead": 0,
    "total": 465
  }
}
```

### `GET /jobs/failed?status=failed,dead&limit=50`
Lists failed/dead reminders with error details.

### `POST /jobs/run?batch_size=50`
Manually trigger a processing run (for debugging/admin).

```json
{
  "processed": 5,
  "succeeded": 4,
  "failed": 1,
  "dead_lettered": 0,
  "recovered": 0,
  "duration_ms": 320.5
}
```

### `POST /jobs/retry-dead?limit=20`
Reset dead-lettered reminders for re-processing.

### `POST /jobs/pause` / `POST /jobs/resume`
Pause or resume the background scheduler.

## Retry Policy

Default configuration:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_retries` | 3 | Maximum delivery attempts |
| `base_delay_seconds` | 60 | Initial retry delay (1 minute) |
| `backoff_factor` | 3.0 | Exponential multiplier |
| `max_delay_seconds` | 3600 | Maximum retry delay (1 hour) |
| `stale_timeout_seconds` | 600 | Stale "sending" detection (10 minutes) |

Retry schedule: 1 min → 3 min → 9 min → dead-letter

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_INTERVAL_SECONDS` | `60` | Scheduler run interval |
| `JOB_BATCH_SIZE` | `50` | Max reminders per run |

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `finmind_job_runs_total` | Counter | Total background job runs |
| `finmind_job_duration_seconds` | Histogram | Job run duration |
| `finmind_reminders_retried_total` | Counter | Retry attempts by channel |
| `finmind_reminders_dead_total` | Counter | Dead-lettered reminders by channel |

## Testing

```bash
# Run job runner tests only
python -m pytest tests/test_job_runner.py -v

# Run full suite
python -m pytest tests/ -v
```

Test coverage:
- RetryPolicy exponential backoff calculation (3 tests)
- Success delivery marks sent (1 test)
- Failure schedules retry with backoff (1 test)
- Dead-letter after max retries (1 test)
- Exception handling (1 test)
- Future reminder skipping (1 test)
- Cross-user batch processing (1 test)
- Stale "sending" crash recovery (1 test)
- Dead-letter reset (1 test)
- Stats aggregation (1 test)
- API endpoints: status, failed, run, retry-dead, status filter (6 tests)

## Migration

For existing PostgreSQL deployments:

```bash
psql -U finmind -d finmind -f app/db/003_resilient_job_retry.sql
```

The `_ensure_schema_compatibility()` function also applies these columns automatically on startup.
