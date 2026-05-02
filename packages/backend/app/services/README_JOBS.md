# Background Job System

A resilient background job execution system with exponential backoff retries and dead-letter queue support.

## Overview

The job system provides:
- **Job Registration**: Map job types to handler functions
- **Automatic Retries**: Exponential backoff on failure (delay = min(2^attempt × 30, 3600) seconds)
- **Dead-Letter Queue**: Jobs that exhaust retries are moved to dead_letter for manual inspection
- **Prometheus Metrics**: Track job execution counts and durations
- **REST API**: Full CRUD for jobs with filtering, pagination, and manual retry/cancel

## Registering Job Types

```python
from app.services.job_runner import job_runner

def send_email(payload):
    user_id = payload["user_id"]
    # ... send email logic ...

def generate_report(payload):
    # ... report generation logic ...
    pass

# Register handlers at startup
job_runner.register("send_email", send_email)
job_runner.register("generate_report", generate_report)
```

Handlers receive the job's `payload` dict (or `None`) and should raise an exception to signal failure. Returning normally signals success.

## Enqueuing Jobs

```python
from app.services.job_runner import job_runner

# With default max_retries (5)
job = job_runner.enqueue_job("send_email", {"user_id": 42, "template": "welcome"})

# With custom max_retries
job = job_runner.enqueue_job("generate_report", {"report_id": 7}, max_retries=3)
```

## Processing Jobs

```python
# Process all pending and retry-ready jobs
processed = job_runner.process_pending()

# Or execute a single job by ID
job = job_runner.execute_job(job_id)
```

## Retry Mechanism

When a job handler raises an exception:

1. **First failure**: Job marked as `FAILED`, scheduled for retry in 60s
2. **Subsequent failures**: Backoff doubles each time (120s, 240s, 480s, ...)
3. **Cap**: Maximum retry delay is 3600s (1 hour)
4. **Dead-letter**: After `max_retries` attempts, job moves to `dead_letter` status

```
Attempt 1: retry in 60s   (2^1 × 30)
Attempt 2: retry in 120s  (2^2 × 30)
Attempt 3: retry in 240s  (2^3 × 30)
Attempt 4: retry in 480s  (2^4 × 30)
Attempt 5: retry in 960s  (2^5 × 30)
Attempt 6: retry in 1920s (2^6 × 30)
Attempt 7+: retry in 3600s (capped)
```

## Job Statuses

| Status | Description |
|---|---|
| `pending` | Waiting to be executed |
| `running` | Currently executing |
| `completed` | Successfully finished |
| `failed` | Failed, waiting for retry |
| `dead_letter` | Exhausted all retries, needs manual intervention |
| `cancelled` | Manually cancelled by user |

## API Endpoints

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### GET /jobs/stats

Returns job statistics: counts by status and recent failures.

```json
{
  "counts": {
    "pending": 5,
    "running": 1,
    "completed": 100,
    "failed": 3,
    "dead_letter": 1,
    "cancelled": 0
  },
  "recent_failures": [...]
}
```

### GET /jobs

List jobs with pagination and optional filters.

Query parameters:
- `page` (default: 1)
- `page_size` (default: 50, max: 200)
- `status` - filter by status (e.g., `pending`, `failed`, `dead_letter`)
- `job_type` - filter by job type (e.g., `send_email`)

```json
{
  "jobs": [...],
  "total": 42,
  "page": 1,
  "page_size": 50
}
```

### GET /jobs/{id}

Get a single job's details.

### POST /jobs/{id}/retry

Manually retry a dead-letter job. Resets the job to pending and executes immediately.

### POST /jobs/{id}/cancel

Cancel a pending job. Only works on jobs with `pending` status.

## Prometheus Metrics

The system exposes two metrics on the `/metrics` endpoint:

- **`finmind_background_jobs_total`** (counter) — Labels: `job_type`, `status`. Incremented each time a job completes or fails.
- **`finmind_background_job_duration_seconds`** (histogram) — Labels: `job_type`. Records execution duration.

### Example PromQL Queries

```promql
# Job failure rate per minute
rate(finmind_background_jobs_total{status="failed"}[5m])

# Average job duration by type
rate(finmind_background_job_duration_seconds_sum[5m]) / rate(finmind_background_job_duration_seconds_count[5m])
```

## Adding a New Job Type

1. Create a handler function in your service:

```python
# app/services/my_service.py
def process_webhook(payload):
    url = payload["url"]
    data = payload["data"]
    # ... process ...
```

2. Register it at startup (in `__init__.py` or wherever appropriate):

```python
from app.services.job_runner import job_runner
from app.services.my_service import process_webhook

job_runner.register("process_webhook", process_webhook)
```

3. Enqueue jobs as needed:

```python
job_runner.enqueue_job("process_webhook", {"url": "...", "data": {...}})
```
