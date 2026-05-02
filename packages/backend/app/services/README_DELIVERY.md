# Reminder Delivery Tracking

Service for tracking reminder delivery reliability and metrics.

## Overview

The `DeliveryTracker` service monitors every reminder delivery attempt, recording
success/failure outcomes and exposing aggregated statistics via REST API and
Prometheus metrics.

## Models

### ReminderDeliveryStatus

Enum defining the lifecycle states of a delivery:

- `PENDING` — delivery has not been attempted yet
- `SENT` — message was dispatched to the provider
- `DELIVERED` — provider confirmed delivery
- `FAILED` — delivery attempt failed (transient or permanent)
- `BOUNCED` — message was rejected by the recipient (e.g. invalid email)

### ReminderDelivery

Tracks per-reminder delivery state:

| Column        | Type        | Description                            |
|---------------|-------------|----------------------------------------|
| id            | Integer PK  | Auto-increment ID                      |
| reminder_id   | FK → reminders | The reminder being tracked           |
| status        | String(20)  | Current delivery status                |
| channel       | String(20)  | Delivery channel (email, whatsapp)     |
| attempts      | Integer     | Number of delivery attempts made       |
| last_error    | Text        | Error message from the last failure    |
| delivered_at  | DateTime    | Timestamp when delivery was confirmed  |
| created_at    | DateTime    | Row creation timestamp                 |
| updated_at    | DateTime    | Row last-update timestamp              |

## Service API

### `delivery_tracker.record_attempt(reminder_id, channel, status, error=None)`

Records a delivery attempt. Creates a new `ReminderDelivery` row if one does not
exist for the given `reminder_id`, otherwise increments the attempt counter.
Sets `delivered_at` when status is `"delivered"`. Also fires a Prometheus
`reminder_events_total` counter via `track_reminder_event()`.

### `delivery_tracker.get_delivery_stats(user_id=None, days=30)`

Returns aggregated delivery statistics for the last N days:

```json
{
  "total": 150,
  "delivered": 140,
  "failed": 8,
  "success_rate": 93.33,
  "avg_attempts": 1.12
}
```

Pass `user_id` to scope results to a specific user.

### `delivery_tracker.get_channel_stats(days=30)`

Returns stats grouped by delivery channel:

```json
{
  "email": {"total": 100, "delivered": 95, "failed": 5},
  "whatsapp": {"total": 50, "delivered": 45, "failed": 3}
}
```

### `delivery_tracker.get_delivery_history(user_id=None, page=1, page_size=20)`

Returns a paginated list of `ReminderDelivery` rows ordered by `created_at`
descending. Returns `(items, total)` tuple.

## REST Endpoints

All endpoints require JWT authentication.

| Method | Path                    | Description                       |
|--------|-------------------------|-----------------------------------|
| GET    | `/delivery/stats`       | Aggregated delivery statistics    |
| GET    | `/delivery/stats/channels` | Per-channel delivery stats     |
| GET    | `/delivery/history`     | Paginated delivery history        |

### Query Parameters

- `days` (int, default 30) — lookback window for stats endpoints
- `page` (int, default 1) — page number for history
- `page_size` (int, default 20, max 100) — items per page for history

## Prometheus Integration

Every `record_attempt()` call emits a `reminder_events_total` counter increment
with labels `event="delivery_attempt"`, `channel`, and `status`. This feeds
into the existing observability pipeline alongside the other reminder events.

## Usage

```python
from app.services.delivery import delivery_tracker

# After sending a reminder
success = send_reminder(reminder)
if success:
    delivery_tracker.record_attempt(reminder.id, reminder.channel, "delivered")
else:
    delivery_tracker.record_attempt(reminder.id, reminder.channel, "failed", error="SMTP timeout")
```
