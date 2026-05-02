# Notification Service

## Overview

The notification service provides a priority-based, grouped notification system
for FinMind. Notifications are created with a priority level and assigned to a
group, enabling users to filter and manage their notification inbox.

## Models

### NotificationPriority

- `low` — informational, no action needed
- `medium` — default priority (standard updates)
- `high` — requires attention soon
- `urgent` — needs immediate action

### NotificationGroup

- `bills` — bill reminders, due dates, autopay events
- `expenses` — expense alerts, recurring expense changes
- `budget` — budget threshold warnings, suggestions
- `security` — login alerts, password changes
- `system` — general system messages, feature announcements

## API Endpoints

All endpoints require JWT authentication.

### POST /notifications

Create a new notification.

```json
{
  "title": "Budget Alert",
  "message": "You have spent 90% of your monthly budget.",
  "priority": "high",
  "group": "budget",
  "action_url": "/dashboard",
  "metadata": {"budget_id": 5, "spent_pct": 90}
}
```

### GET /notifications

List notifications with optional filters.

Query parameters:
- `unread_only` — `true` to return only unread notifications
- `group` — filter by group name
- `page` — page number (default: 1)
- `page_size` — items per page (default: 20, max: 100)

### GET /notifications/unread-count

Returns total unread count and per-group breakdown.

### PATCH /notifications/<id>/read

Mark a single notification as read.

### PATCH /notifications/read-all

Mark all notifications as read. Optional `group` query parameter to scope.

### DELETE /notifications/<id>

Delete a notification permanently.

## Usage from Code

```python
from app.services.notifications import notification_service

# Create a notification
notification_service.create(
    user_id=1,
    title="Bill Due Tomorrow",
    message="Electricity bill of $90 is due tomorrow.",
    priority="high",
    group="bills",
    action_url="/bills/3",
    metadata={"bill_id": 3},
)

# Get unread counts
counts = notification_service.get_unread_count(user_id=1)
# {"bills": 2, "budget": 1}
```
