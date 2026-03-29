# Reminder Reliability Tracking

This document describes the reminder delivery tracking and reliability metrics system implemented in FinMind.

## Overview

The reminder reliability tracking system provides:

- **Delivery Status Tracking**: Know whether reminders were successfully delivered
- **Retry Logic**: Automatic retries with exponential backoff for failed deliveries
- **Reliability Metrics**: Track success rates, response times, and channel performance
- **Failure Management**: View and manually retry failed reminders

## Features

### 1. Delivery Tracking

Each reminder now tracks:
- `delivered`: Boolean indicating delivery success/failure
- `delivery_attempts`: Number of delivery attempts made
- `last_attempt_at`: Timestamp of last delivery attempt
- `error_message`: Error details if delivery failed

### 2. Automatic Retry Logic

Failed deliveries are automatically retried with exponential backoff:
- **Attempt 1**: Immediate
- **Attempt 2**: 5 minutes delay
- **Attempt 3**: 15 minutes delay
- **Attempt 4+**: 60 minutes delay (if extended)

After 3 failed attempts, the reminder is marked as failed and requires manual retry.

### 3. Delivery History

Each delivery attempt is recorded in the `reminder_deliveries` table with:
- Success/failure status
- Channel used (email/WhatsApp)
- Response time (latency)
- Error messages
- Timestamp

## API Endpoints

### Get Delivery Metrics
```
GET /api/reminders/metrics?days=30
```

Returns reliability metrics for the authenticated user:
```json
{
  "period_days": 30,
  "total_attempts": 100,
  "successful_deliveries": 95,
  "failed_deliveries": 5,
  "success_rate": 95.0,
  "average_response_time_ms": 250,
  "by_channel": {
    "email": {
      "attempts": 80,
      "successful": 78,
      "success_rate": 97.5
    },
    "whatsapp": {
      "attempts": 20,
      "successful": 17,
      "success_rate": 85.0
    }
  }
}
```

### Get Failed Reminders
```
GET /api/reminders/failed?limit=10
```

Returns reminders that exhausted all retry attempts.

### Retry a Failed Reminder
```
POST /api/reminders/{id}/retry
```

Manually retry a failed reminder immediately.

### Get Reminder Delivery History
```
GET /api/reminders/{id}/deliveries
```

Returns the complete delivery attempt history for a specific reminder.

### Process Due Reminders (Updated)
```
POST /api/reminders/run
```

Now returns detailed results:
```json
{
  "processed": 5,
  "delivered": 4,
  "failed": 1
}
```

## Database Schema

### Updated `reminders` Table
```sql
ALTER TABLE reminders ADD COLUMN delivered BOOLEAN;
ALTER TABLE reminders ADD COLUMN delivery_attempts INTEGER DEFAULT 0;
ALTER TABLE reminders ADD COLUMN last_attempt_at TIMESTAMP;
ALTER TABLE reminders ADD COLUMN error_message VARCHAR(500);
ALTER TABLE reminders ADD COLUMN created_at TIMESTAMP DEFAULT NOW();
```

### New `reminder_deliveries` Table
```sql
CREATE TABLE reminder_deliveries (
  id SERIAL PRIMARY KEY,
  reminder_id INTEGER REFERENCES reminders(id),
  attempted_at TIMESTAMP DEFAULT NOW(),
  success BOOLEAN NOT NULL,
  channel VARCHAR(20) NOT NULL,
  error_message VARCHAR(500),
  response_time_ms INTEGER
);
```

## Migration

Run the migration script to add the new schema:

```bash
cd packages/backend
python migrations/add_reminder_delivery_tracking.py
```

Or if using Alembic:
```bash
alembic upgrade add_reminder_delivery_tracking
```

## Testing

Run the reminder delivery tests:

```bash
cd packages/backend
pytest app/tests/test_reminder_delivery.py -v
```

Tests cover:
- Email/WhatsApp delivery success and failure
- Retry logic with exponential backoff
- Metrics calculation
- Failed reminder retrieval
- Manual retry functionality

## Monitoring

To monitor reminder reliability:

1. **Check metrics regularly** via the `/api/reminders/metrics` endpoint
2. **Review failed reminders** via `/api/reminders/failed`
3. **Set up alerts** when success rate drops below a threshold (e.g., 90%)

## Future Enhancements

Potential improvements:
- Webhook notifications for delivery failures
- Email alerts to admins when reliability drops
- Dashboard visualization of metrics
- Export metrics to external monitoring (Prometheus/Grafana)
