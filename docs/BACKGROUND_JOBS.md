# Resilient Background Job System

This document describes the resilient background job system implemented for FinMind, providing retry logic, monitoring, and dead letter queue capabilities.

## Overview

The job system uses **Celery** with **Redis** as the broker and backend, providing:

- **Reliable task execution** with automatic retries
- **Exponential backoff** for transient failures
- **Dead letter queue** for failed tasks requiring manual intervention
- **Comprehensive monitoring** via Prometheus metrics and Flower UI
- **Priority queues** (high, default, low) for different workload types

## Architecture

```
┌─────────────┐     ┌─────────┐     ┌─────────────────┐
│   Flask     │────▶│  Redis  │────▶│ Celery Workers  │
│   Backend   │     │  Broker │     │                 │
└─────────────┘     └─────────┘     └─────────────────┘
                                           │
                    ┌─────────┐            │
                    │  Redis  │◀───────────┘
                    │ Backend │            (results, monitoring)
                    └─────────┘
```

## Task Queues

| Queue | Purpose | Workers |
|-------|---------|---------|
| `high_priority` | Reminders, notifications | 2 concurrent |
| `default` | AI processing, general tasks | 4 concurrent |
| `low_priority` | Reports, cleanup, batch jobs | 2 concurrent |
| `dead_letter` | Failed tasks for manual review | - |

## Retry Strategy

Tasks use exponential backoff with the following defaults:

```python
# Retry delays: 60s, 120s, 240s, 480s, 960s (max 1 hour)
countdown = min(2 ** retries * 60, 3600)
```

- **Max retries**: 5 attempts for most tasks
- **Max retry delay**: 1 hour
- **Time limits**: 60s soft, 300s hard for most tasks

## Task Types

### Reminder Tasks (`tasks.reminders`)

```python
# Send a reminder notification
send_reminder_task.delay(reminder_id=123)

# Process all due reminders (called by beat scheduler)
process_due_reminders.delay()

# Cleanup old logs
cleanup_old_reminders.delay(days=30)
```

### AI Tasks (`tasks.ai`)

```python
# Generate insights for a user
generate_insights_task.delay(user_id=1, period="monthly")

# Process expense receipt
process_expense_receipt_task.delay(
    expense_id=456,
    receipt_url="https://...",
    ocr_provider="openai"
)
```

### Report Tasks (`tasks.reports`)

```python
# Generate weekly report
generate_weekly_report_task.delay(user_id=1)

# Generate monthly digest
generate_monthly_digest_task.delay(user_id=1, month=3, year=2026)

# Schedule reports for all users (called by beat)
schedule_all_weekly_reports.delay()
```

## Dead Letter Queue

Tasks that exhaust all retries are sent to the dead letter queue for manual review:

```bash
# List dead letter items
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/tasks/dead-letter

# Retry a specific item
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "dead_letter:reminders:123"}' \
  http://localhost:5000/api/tasks/dead-letter/retry
```

## Monitoring

### Task Statistics API

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/tasks/stats
```

Response:
```json
{
  "active_tasks": 5,
  "completed_24h": 120,
  "failed_7d": 3,
  "retries_24h": 15,
  "dead_letter": 1,
  "timestamp": "2026-03-21T10:00:00Z"
}
```

### Flower UI

Access the Celery monitoring UI at `http://localhost:5555` when running with Docker Compose.

### Prometheus Metrics

Available at `/metrics`:

- `celery_task_executions_total` - Task execution counts by status
- `celery_task_execution_duration_seconds` - Execution duration histogram
- `celery_task_retries_total` - Retry counts
- `celery_task_failures_total` - Failure counts by exception type
- `celery_active_tasks` - Currently running tasks

## Running with Docker

Start the full stack including Celery workers:

```bash
docker-compose -f docker-compose.celery.yml up -d
```

Services:
- `backend` - Flask API
- `celery-worker-default` - Default queue worker
- `celery-worker-high` - High priority queue worker
- `celery-worker-low` - Low priority queue worker
- `celery-beat` - Task scheduler
- `flower` - Monitoring UI (port 5555)
- `postgres` - Database
- `redis` - Broker and cache

## Scheduled Tasks

Celery beat runs the following periodic tasks:

| Task | Schedule | Description |
|------|----------|-------------|
| `process_due_reminders` | Every 60 seconds | Check and queue due reminders |
| `schedule_all_weekly_reports` | Sundays at 9 AM | Generate weekly reports for all users |
| `cleanup_old_reminders` | Daily at 3 AM | Remove old notification logs (30 days) |

## Development

### Running Tests

```bash
cd packages/backend
pytest tests/tasks/ -v
```

### Manual Task Execution

```python
from app.tasks.reminders import send_reminder_task

# Run synchronously (for testing)
result = send_reminder_task.run(reminder_id=123)

# Run asynchronously (production)
task = send_reminder_task.delay(reminder_id=123)
print(task.id)  # Track task ID
```

### Monitoring Task Status

```python
from app.celery_config import celery_app

# Check task result
task = celery_app.AsyncResult(task_id)
print(task.status)  # PENDING, SUCCESS, FAILURE, RETRY
print(task.result)  # Return value or exception
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker/backend |
| `CELERY_BROKER_URL` | Same as REDIS_URL | Celery broker |
| `CELERY_RESULT_BACKEND` | Same as REDIS_URL | Result backend |
| `LOG_LEVEL` | `INFO` | Worker log level |

## Best Practices

1. **Always use `.delay()` or `.apply_async()`** for production code
2. **Set appropriate retry counts** - Use fewer retries for time-sensitive tasks
3. **Monitor dead letter queue** - Review and retry failed tasks regularly
4. **Use priority queues** - Route urgent tasks to `high_priority` queue
5. **Handle idempotency** - Tasks should be safe to run multiple times
6. **Set time limits** - Prevent runaway tasks from consuming resources

## Troubleshooting

### Workers not processing tasks

```bash
# Check worker status
docker-compose -f docker-compose.celery.yml logs celery-worker-default

# Inspect Redis for pending tasks
redis-cli llen celery
```

### Tasks stuck in retry

```bash
# Check retry queue
redis-cli keys "task:retry:*"

# Inspect specific task
redis-cli get "task:retry:<task_id>"
```

### High failure rate

Check Flower UI or metrics endpoint for:
- Exception types causing failures
- Tasks with high retry counts
- Worker resource utilization

## Security Considerations

- Tasks run with full database access - validate all inputs
- Sanitize user-provided data before queuing tasks
- Use Celery's built-in serialization (JSON) - avoid pickle
- Monitor for unusual task patterns or queue buildup
