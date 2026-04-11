# Resilient Background Job Retry & Monitoring

> Implements bounty [#130](https://github.com/rohitdash08/FinMind/issues/130) — Resilient background job retry & monitoring.

## Overview

This implementation adds a complete background job execution system to FinMind with:

- **JobExecution model** — tracks job lifecycle (PENDING → RUNNING → SUCCESS/RETRYING/DEAD)
- **Exponential backoff retry** — configurable policy (default: 5min → 15min → 45min, max 3 attempts)
- **Dead-letter queue** — permanently failed jobs with manual retry capability
- **Monitoring API** — job statistics, filtering, and dead-letter management
- **Scheduler tick** — processes pending and due retrying jobs

## Architecture

### Models

**`JobStatus` enum**: `PENDING | RUNNING | SUCCESS | FAILED | RETRYING | DEAD`

**`JobType` enum**: `REMINDER | EMAIL | WHATSAPP | IMPORT | INSIGHT | CUSTOM`

**`JobExecution` model** (`job_executions` table):
| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PK | Auto-increment ID |
| `job_type` | job_type | Category of the job |
| `status` | job_status | Current lifecycle state |
| `payload` | TEXT | JSON-serialized job data |
| `result` | TEXT | Success output or error message |
| `attempt` | INT | Current attempt number |
| `max_attempts` | INT | Maximum retries before dead-lettering |
| `next_retry_at` | TIMESTAMP | When the next retry is due |
| `created_at` | TIMESTAMP | Job creation time |
| `started_at` | TIMESTAMP | First execution start time |
| `completed_at` | TIMESTAMP | Successful completion time |
| `dead_reason` | TEXT | Error message for dead-lettered jobs |
| `dead_at` | TIMESTAMP | When the job was dead-lettered |
| `source_id` | INT | FK to originating entity (e.g. reminder.id) |
| `source_type` | VARCHAR(50) | Type of originating entity |

### RetryPolicy

Configurable exponential backoff with environment variable support:

```python
# Environment variables (with defaults)
JOB_RETRY_MAX_ATTEMPTS=3      # Max retry attempts
JOB_RETRY_BASE_DELAY_MIN=5    # Base delay in minutes
JOB_RETRY_MAX_DELAY_MIN=60    # Maximum delay cap in minutes
JOB_RETRY_BACKOFF_FACTOR=3.0  # Exponential multiplier
```

Default schedule: **5min → 15min → 45min** (factor of 3, capped at 60min).

### API Endpoints

All endpoints require JWT authentication.

| Method | Path | Description |
|---|---|---|
| `GET` | `/jobs/stats` | Aggregate job statistics |
| `GET` | `/jobs` | List/search job executions |
| `GET` | `/jobs/<id>` | Single job detail |
| `POST` | `/jobs/<id>/retry` | Retry a dead-lettered job |

**Query parameters for `GET /jobs`:**
- `status` — filter by status (PENDING, RUNNING, SUCCESS, FAILED, RETRYING, DEAD)
- `job_type` — filter by type (REMINDER, EMAIL, WHATSAPP, IMPORT, INSIGHT, CUSTOM)
- `limit` — page size (max 200, default 50)
- `offset` — pagination offset (default 0)

**Example response for `GET /jobs/stats`:**
```json
{
  "total": 42,
  "by_status": {"SUCCESS": 35, "DEAD": 3, "PENDING": 2, "RETRYING": 2},
  "by_type": {"REMINDER": 30, "EMAIL": 10, "CUSTOM": 2},
  "success_rate": 92.1,
  "avg_duration_seconds": 1.24,
  "recent_dead": [...]
}
```

### Scheduler Integration

The `tick()` function processes all due jobs:

```python
from app.services.jobs import tick

# Call periodically (e.g. via APScheduler or cron)
result = tick()
# Returns: {"processed": N, "success": N, "failed": N}
```

### Reminder Integration

Failed reminder sends are now automatically enqueued as REMINDER jobs for retry:

```python
# Before (fire-and-forget):
send_reminder(r)
r.sent = True

# After (resilient):
success = send_reminder(r)
if success:
    r.sent = True
else:
    dispatch_job(JobType.REMINDER, '{"reminder_id": r.id}', source_id=r.id, source_type="reminder")
```

### Database Migration

The `job_executions` table is created automatically on app startup via `_ensure_job_executions_table()`. For manual setup:

```bash
flask init-db
```

Or run the SQL in `db/schema.sql` — the `job_status` and `job_type` enums and `job_executions` table are included.

## Testing

38 tests covering:

- **RetryPolicy** — exponential backoff calculations, env config, max delay capping
- **Job lifecycle** — dispatch → running → success, retry scheduling, dead-lettering
- **Dead-letter retry** — manual reset of dead-lettered jobs
- **Scheduler tick** — pending/retrying job processing
- **Monitoring** — stats aggregation, duration tracking
- **REST API** — all endpoints with auth, filtering, pagination, error cases
- **Integration** — reminder-to-job dispatch on send failure

```bash
cd packages/backend
python3 -m pytest tests/test_jobs.py -v
```

## Files Changed

| File | Change |
|---|---|
| `app/models.py` | Added `JobStatus`, `JobType`, `JobExecution` model |
| `app/services/jobs.py` | **New** — RetryPolicy, dispatch/mark functions, tick, stats |
| `app/routes/jobs.py` | **New** — Monitoring API endpoints |
| `app/routes/__init__.py` | Registered jobs blueprint |
| `app/routes/reminders.py` | Integrated resilient job dispatch on send failure |
| `app/__init__.py` | Added `_ensure_job_executions_table()` migration |
| `app/db/schema.sql` | Added `job_status`, `job_type` enums and `job_executions` table |
| `tests/test_jobs.py` | **New** — 38 comprehensive tests |

## Design Decisions

1. **Pure dispatch function** — `dispatch_job()` only creates a DB record, making it fully testable without side effects
2. **Configurable retry policy** — Environment variables allow ops teams to tune without code changes
3. **Idempotent schema migration** — `_ensure_job_executions_table()` is safe to run on every startup
4. **Dead-letter queue with manual retry** — Failed jobs aren't silently dropped; operators can retry them via API
5. **Minimal coupling** — Only the reminders route was modified; other job types can be added incrementally