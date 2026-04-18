# Background Job Queue

FinMind uses a resilient background job queue system for asynchronous task execution with automatic retry and monitoring.

## Architecture

```
┌──────────────┐     ┌───────────┐     ┌──────────────┐
│   API / CLI  │────>│   Redis   │────>│  APScheduler │
│  (enqueue)   │     │  (queue)  │     │   (worker)   │
└──────────────┘     └───────────┘     └──────┬───────┘
                                              │
                   ┌──────────────────────────┤
                   │                          │
              ┌────▼─────┐            ┌───────▼──────┐
              │ PostgreSQL│            │ Dead-Letter  │
              │ (status)  │            │   Queue      │
              └──────────┘            └──────────────┘
```

## Features

- **Redis-backed queue** with priority support (lower number = higher priority)
- **Exponential backoff retry** with configurable max retries (default: 5)
- **Dead-letter queue** for permanently failed jobs
- **Job status tracking** in PostgreSQL
- **Distributed locking** to prevent duplicate execution
- **APScheduler integration** for automatic job processing
- **Prometheus metrics** for monitoring

## API Endpoints

All endpoints require JWT authentication.

### List Jobs
```
GET /api/jobs?status=pending&job_type=send_reminder&limit=50&offset=0
```

### Get Job Status
```
GET /api/jobs/<job_id>
```

### Cancel Job
```
POST /api/jobs/<job_id>/cancel
```

### Retry Dead Job
```
POST /api/jobs/<job_id>/retry
```

### Queue Statistics
```
GET /api/jobs/stats
```

### Enqueue Job
```
POST /api/jobs/enqueue
Content-Type: application/json

{
  "job_type": "send_reminder",
  "payload": {"reminder_id": 123},
  "queue": "default",
  "priority": 5,
  "max_retries": 5
}
```

## Job Types

### `send_reminder`
Send a bill reminder notification (email or WhatsApp).

```json
{"reminder_id": 123}
```

### `import_expenses`
Import expenses from a CSV file.

```json
{"file_path": "/tmp/import.csv", "user_id": 42}
```

## Adding Custom Handlers

Register new job types using the `register_handler` decorator:

```python
from app.services.job_worker import register_handler

@register_handler("my_custom_job")
def handle_my_job(payload: dict) -> dict:
    # Your logic here
    return {"status": "done"}
```

## Retry Behavior

| Attempt | Delay |
|---------|-------|
| 1       | 5s    |
| 2       | 10s   |
| 3       | 20s   |
| 4       | 40s   |
| 5       | 80s   |
| ...     | ...   |
| max     | 1h    |

After `max_retries` attempts, jobs are moved to the dead-letter queue and can be manually retried via the API.

## Prometheus Metrics

- `finmind_jobs_enqueued_total` — Total jobs enqueued
- `finmind_jobs_completed_total` — Total jobs completed
- `finmind_jobs_failed_total` — Total job failures (including retries)
- `finmind_jobs_dead_total` — Total jobs moved to dead-letter queue
- `finmind_job_duration_seconds` — Job execution duration histogram
- `finmind_queue_depth` — Current queue depth

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `DATABASE_URL` | — | PostgreSQL connection URL |

## Testing

```bash
cd packages/backend
pytest tests/test_jobs.py -v
```
