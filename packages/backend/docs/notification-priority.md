# Notification Priority & Grouping System

Intelligent notification management with priority levels, category-based grouping, batch operations, and analytics.

## Overview

- **Priority sorting** — Critical, high, normal, low with weighted ordering
- **Category system** — general, bill_due, budget_alert, transaction, security, insight, reminder, system
- **Grouping** — Collapse related notifications by group_key
- **Batch operations** — Mark all read, dismiss entire groups
- **Analytics** — Read rates, volume trends, priority/category breakdowns

## Database Schema

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal',
    category VARCHAR(50) DEFAULT 'general',
    group_key VARCHAR(100),
    is_read BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE,
    action_url VARCHAR(500),
    action_type VARCHAR(50),
    extra_data JSONB DEFAULT '{}',
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## API Endpoints

All endpoints require JWT authentication.

### Create Notification

```http
POST /notifications/send
{
    "title": "Bill Due Tomorrow",
    "message": "Your rent payment of $1,200 is due tomorrow",
    "priority": "high",
    "category": "bill_due",
    "group_key": "bills_march",
    "action_url": "/bills/42",
    "action_type": "navigate"
}
```

### List Notifications (Priority-Sorted)

```http
GET /notifications?category=bill_due&priority=high&is_read=false&limit=20&offset=0
```

Returns notifications sorted by priority weight descending, then by recency.

### Grouped View

```http
GET /notifications/grouped?category=security
```

Groups notifications by `group_key` with counts and unread tallies.

### Mark Read

```http
POST /notifications/<id>/read
POST /notifications/read-all
```

### Dismiss

```http
POST /notifications/<id>/dismiss
POST /notifications/dismiss-group  {"group_key": "bills_march"}
```

### Unread Counts

```http
GET /notifications/unread
```

Returns total count with breakdowns by priority and category.

### Statistics

```http
GET /notifications/stats?days=30
```

Returns read rates, volume trends, priority/category breakdowns.

## Priority Weights

| Priority | Weight | Use Case |
|----------|--------|----------|
| critical | 4 | Security alerts, overdue bills |
| high | 3 | Due tomorrow, budget exceeded |
| normal | 2 | Transaction notifications |
| low | 1 | Tips, insights |

## Architecture

| Component | File |
|-----------|------|
| Migration | `app/db/034_notification_priority.sql` |
| Model | `app/models.py` → `Notification` |
| Service | `app/services/notification_priority.py` |
| Routes | `app/routes/notification_priority.py` |
| Tests | `tests/test_notification_priority.py` |

## Testing

```bash
python -m pytest tests/test_notification_priority.py -v
# 38 tests covering priority sorting, grouping, batch ops, and route integration
```
