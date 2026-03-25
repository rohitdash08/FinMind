# Background Job System

## Overview

The background job system provides robust asynchronous task execution with automatic retry and monitoring capabilities.

## Features

- **Exponential Backoff Retry**: Jobs that fail are automatically retried with exponentially increasing delays
- **Dead Letter Queue**: Permanently failed jobs are stored for inspection and manual retry
- **Priority Queue**: Jobs can be prioritized to ensure critical tasks are processed first
- **Metrics & Monitoring**: Built-in metrics tracking for job success rates, processing times, and failures
- **Configurable Retry Policies**: Customize retry behavior per job type

## Usage

### Creating a Job

```python
from app.services.background_jobs import BackgroundJobService, JobType

# Enqueue a new job
job = BackgroundJobService.enqueue(
    job_type=JobType.SEND_EMAIL,
    payload={
        "to": "user@example.com",
        "subject": "Welcome!",
        "body": "Welcome to FinMind"
    },
    priority=10,  # Higher priority = processed first
    max_retries=3,  # Default is 3
    user_id=123  # Optional: associate with user
)
```

### Registering a Job Handler

```python
from app.services.background_jobs import BackgroundJobService, JobType

def send_email_handler(payload: dict) -> dict:
    # Your email sending logic here
    send_email(
        to=payload["to"],
        subject=payload["subject"],
        body=payload["body"]
    )
    return {"sent": True}

# Register the handler
BackgroundJobService.register_handler(JobType.SEND_EMAIL, send_email_handler)
```

### Processing Jobs

In production, use a background worker process:

```python
# In a worker process
from app.services.background_jobs import BackgroundJobService

while True:
    stats = BackgroundJobService.process_pending_jobs(limit=10)
    time.sleep(1)  # Wait before next batch
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs/metrics` | GET | Get aggregated job metrics |
| `/api/jobs/<id>` | GET | Get status of specific job |
| `/api/jobs/pending` | GET | List pending and retrying jobs |
| `/api/jobs/dead-letter` | GET | List failed jobs in dead letter queue |
| `/api/jobs/<id>/retry` | POST | Manually retry a dead letter job |
| `/api/jobs/process` | POST | Manually trigger job processing |
| `/api/jobs/cleanup` | POST | Clean up old completed jobs |
| `/api/jobs/health` | GET | Health check for job system |

## Retry Configuration

Default retry behavior:
- **Initial Delay**: 1 second
- **Max Delay**: 5 minutes (300 seconds)
- **Backoff Multiplier**: 2x
- **Max Retries**: 3
- **Jitter**: Enabled (±25% random variation)

Custom configuration:

```python
from app.services.background_jobs import create_retry_config

config = create_retry_config(
    max_retries=5,
    initial_delay=2.0,
    max_delay=600.0,
    backoff_multiplier=3.0,
    jitter=True
)
```

## Job Status Flow

```
PENDING → RUNNING → SUCCEEDED
                    ↓
                 FAILED → RETRYING → RUNNING
                    ↓              (if retry_count < max_retries)
                 DEAD_LETTER
```

## Monitoring

Access metrics at `/api/jobs/metrics`:

```json
{
  "jobs_created": 150,
  "jobs_succeeded": 142,
  "jobs_failed": 3,
  "jobs_retried": 8,
  "jobs_dead_letter": 5,
  "avg_processing_time_ms": 125.5
}
```

## Database Schema

Jobs are stored in the `background_jobs` table with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| job_type | VARCHAR(50) | Type of job |
| payload | JSONB | Job-specific data |
| status | VARCHAR(20) | Current status |
| priority | INTEGER | Processing priority (higher = urgent) |
| retry_count | INTEGER | Number of retries attempted |
| max_retries | INTEGER | Maximum retry attempts |
| next_retry_at | TIMESTAMP | When to retry next |
| last_error | TEXT | Error from last failure |
| created_at | TIMESTAMP | Job creation time |
| started_at | TIMESTAMP | Processing start time |
| completed_at | TIMESTAMP | Completion time |
| result | JSONB | Job result data |
| user_id | INTEGER | Associated user (optional) |

## Best Practices

1. **Keep handlers idempotent**: Jobs may be retried, so handlers should handle duplicate execution gracefully
2. **Use appropriate priorities**: Reserve high priorities for time-sensitive tasks
3. **Monitor dead letter queue**: Regularly check for failed jobs and investigate root causes
4. **Set reasonable timeouts**: Long-running jobs should have their own timeout logic
5. **Log appropriately**: Include job ID in logs for troubleshooting