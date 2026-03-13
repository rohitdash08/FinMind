# Background Job Manager

FinMind includes a resilient background job manager that automatically processes
scheduled tasks (like reminders) with built-in retry logic, monitoring, and
crash recovery.

## Architecture

The job manager wraps APScheduler with:

- **Automatic retry** with configurable exponential backoff
- **Dead-letter tracking** for jobs that exhaust all retries
- **Per-job execution history** with timing and error details
- **Prometheus metrics** for observability
- **Redis-backed persistence** for crash recovery
- **Admin API endpoints** for monitoring and management

## How It Works

### Job Lifecycle

```
PENDING → RUNNING → SUCCESS
                  ↘ RETRYING → RUNNING → SUCCESS
                             ↘ RETRYING → ... → FAILED (dead-lettered)
```

When a job fails:
1. The error is logged with full traceback
2. Retry delay is calculated using exponential backoff
3. A one-shot retry is scheduled after the delay
4. If max retries are exhausted, the job is **dead-lettered** (skipped on future triggers)
5. An admin can reset dead-lettered jobs via the API

### Crash Recovery

Job state is persisted to Redis after every execution. On restart:
- Previous state is restored from Redis
- Jobs that were `RUNNING` when the process crashed are marked as `RETRYING`
- The scheduler resumes with correct attempt counts

## Configuration

### Retry Policy

Each job can have its own retry policy:

```python
from app.services.job_manager import job_manager, RetryPolicy

job_manager.add_job(
    my_function,
    job_id="my_job",
    trigger="interval",
    retry_policy=RetryPolicy(
        max_retries=5,           # attempts before dead-letter
        base_delay_seconds=10.0, # initial retry delay
        max_delay_seconds=600.0, # cap on retry delay
        backoff_factor=2.0,      # exponential multiplier
    ),
    minutes=5,  # run every 5 minutes
)
```

### Default Retry Policy

If no policy is specified, jobs use:
- 3 retries
- 5s initial delay, 2x backoff, 300s max

## API Endpoints

### `GET /jobs/health` (unauthenticated)

Health check for monitoring systems. Returns 200 if all jobs are healthy,
503 if any job is failed or missed.

```json
{
  "healthy": true,
  "jobs": {
    "process_due_reminders": {
      "healthy": true,
      "status": "success",
      "total_runs": 42,
      "total_failures": 0
    }
  }
}
```

### `GET /jobs/status` (admin only)

Detailed status including execution history.

### `GET /jobs/dead-letters` (admin only)

List jobs that exhausted all retries.

### `POST /jobs/<job_id>/reset` (admin only)

Reset a dead-lettered job so it retries on the next trigger.

## Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `finmind_job_executions_total` | Counter | `job_id`, `status` | Total executions |
| `finmind_job_retries_total` | Counter | `job_id` | Retry attempts |
| `finmind_job_dead_letters_total` | Counter | `job_id` | Dead-lettered jobs |
| `finmind_job_duration_seconds` | Histogram | `job_id` | Execution duration |
| `finmind_jobs_active` | Gauge | — | Currently running jobs |

## Adding New Jobs

```python
# In app/__init__.py or a dedicated jobs module

def my_periodic_task():
    """Runs inside Flask app context automatically."""
    # Your business logic here
    pass

job_manager.add_job(
    my_periodic_task,
    job_id="my_periodic_task",
    trigger="cron",
    hour=9,
    minute=0,
)
```

The job manager handles:
- Running the function inside the Flask app context
- Catching and logging exceptions
- Retrying on failure
- Recording metrics and history
- Persisting state to Redis
