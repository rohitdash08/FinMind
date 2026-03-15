# Reminder Reliability Tracking & Delivery Metrics

Track every reminder delivery attempt with full lifecycle visibility — from initial send through delivery confirmation, bounce handling, and engagement tracking.

## Overview

The reminder tracking system provides comprehensive delivery observability:

- **Delivery lifecycle** — Record attempts, confirmations, failures, and bounces
- **Engagement tracking** — Track opens and clicks for each delivery
- **Reliability metrics** — Calculate delivery rates, failure rates, and latency
- **Channel performance** — Compare effectiveness across email, push, SMS, and in-app channels

## Database Schema

```sql
CREATE TABLE reminder_deliveries (
    id SERIAL PRIMARY KEY,
    reminder_id INTEGER NOT NULL REFERENCES reminders(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    channel VARCHAR(20) DEFAULT 'email',
    status VARCHAR(20) DEFAULT 'pending',
    attempt_number INTEGER DEFAULT 1,
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    failed_at TIMESTAMP,
    failure_reason TEXT,
    response_code VARCHAR(10),
    latency_ms INTEGER,
    opened BOOLEAN DEFAULT FALSE,
    opened_at TIMESTAMP,
    clicked BOOLEAN DEFAULT FALSE,
    clicked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## API Endpoints

All endpoints require JWT authentication.

### Record Delivery Attempt

```http
POST /tracking/record
Content-Type: application/json
Authorization: Bearer <token>

{
    "reminder_id": 42,
    "channel": "email"
}
```

**Response** `201 Created`:

```json
{
    "id": 1,
    "reminder_id": 42,
    "status": "pending",
    "attempt_number": 1,
    "channel": "email"
}
```

### Update Delivery Status

```http
POST /tracking/<delivery_id>/sent
POST /tracking/<delivery_id>/delivered
POST /tracking/<delivery_id>/failed
POST /tracking/<delivery_id>/bounced
```

Each accepts optional JSON body:

| Endpoint     | Optional Fields                    |
|-------------|-----------------------------------|
| `/sent`     | `response_code`                   |
| `/delivered`| `latency_ms`                      |
| `/failed`   | `reason`, `response_code`         |
| `/bounced`  | `reason`                          |

### Track Engagement

```http
POST /tracking/<delivery_id>/opened
POST /tracking/<delivery_id>/clicked
```

Clicking automatically marks as opened.

### Query Delivery History

```http
GET /tracking/history?channel=email&status=delivered&limit=50
```

Returns all deliveries for the authenticated user with optional filters.

### Get Reminder Deliveries

```http
GET /tracking/reminder/<reminder_id>
```

Returns all delivery attempts for a specific reminder.

### Reliability Metrics

```http
GET /tracking/metrics?days=30
```

**Response**:

```json
{
    "total_attempts": 150,
    "delivered": 142,
    "failed": 5,
    "bounced": 3,
    "delivery_rate": 0.947,
    "failure_rate": 0.033,
    "bounce_rate": 0.02,
    "open_rate": 0.65,
    "click_rate": 0.12,
    "avg_latency_ms": 245,
    "period_days": 30,
    "by_channel": { "email": 100, "push": 50 },
    "by_status": { "delivered": 142, "failed": 5, "bounced": 3 }
}
```

### Channel Performance

```http
GET /tracking/channels?days=30
```

**Response**:

```json
{
    "channels": [
        {
            "channel": "email",
            "total": 100,
            "delivered": 95,
            "delivery_rate": 0.95,
            "avg_latency_ms": 320
        },
        {
            "channel": "push",
            "total": 50,
            "delivered": 47,
            "delivery_rate": 0.94,
            "avg_latency_ms": 85
        }
    ],
    "period_days": 30
}
```

## Delivery Status Flow

```
pending → sent → delivered
                ↘ failed
                ↘ bounced
```

## Architecture

| Component | File |
|-----------|------|
| Migration | `app/db/033_reminder_tracking.sql` |
| Model | `app/models.py` → `ReminderDelivery` |
| Service | `app/services/reminder_tracking.py` |
| Routes | `app/routes/reminder_tracking.py` |
| Tests | `tests/test_reminder_tracking.py` |

## Testing

```bash
python -m pytest tests/test_reminder_tracking.py -v
# 36 tests covering service logic, status transitions, engagement tracking, and route integration
```
