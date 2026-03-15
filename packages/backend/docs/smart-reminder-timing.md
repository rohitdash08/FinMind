# Smart Reminder Timing Optimization

## Overview

Analyzes user activity patterns to determine optimal reminder delivery times. Respects quiet hours, interval constraints, and daily limits. Uses historical engagement data to learn when users are most responsive.

## Database Tables

### `user_activity_logs`
| Column | Type | Description |
|---|---|---|
| id | SERIAL PK | Auto-increment ID |
| user_id | INTEGER FK | References users(id) |
| action | VARCHAR(50) | Activity type (e.g. app_open, expense_added) |
| hour_of_day | INTEGER | Hour 0-23 when activity occurred |
| day_of_week | INTEGER | Day 0-6 (Mon-Sun) |
| created_at | TIMESTAMP | When the activity was logged |

### `reminder_preferences`
| Column | Type | Default | Description |
|---|---|---|---|
| id | SERIAL PK | | Auto-increment ID |
| user_id | INTEGER FK | | References users(id), UNIQUE |
| preferred_hour | INTEGER | 9 | Default reminder hour |
| preferred_days | VARCHAR(50) | "1,2,3,4,5" | Comma-separated day numbers |
| quiet_hours_start | INTEGER | 22 | Quiet period start hour |
| quiet_hours_end | INTEGER | 7 | Quiet period end hour |
| auto_optimize | BOOLEAN | TRUE | Enable ML-based optimization |
| min_interval_hours | INTEGER | 4 | Minimum hours between reminders |
| max_reminders_per_day | INTEGER | 5 | Maximum daily reminders |

## API Endpoints

All endpoints require JWT authentication.

### Log Activity
```
POST /smart-reminders/activity
Body: { "action": "app_open" }
Response: { "id": 1, "action": "app_open", "hour_of_day": 10, "day_of_week": 3 }
```

### Get Activity Pattern
```
GET /smart-reminders/activity/pattern
Response: {
  "total_activities": 42,
  "hourly_distribution": { "0": 0, "1": 0, ..., "10": 15, ... },
  "daily_distribution": { "0": 8, "1": 12, ... },
  "peak_hours": [10, 14, 16],
  "peak_days": [1, 3, 5],
  "most_active_hour": 10,
  "most_active_day": 1
}
```

### Get Preferences
```
GET /smart-reminders/preferences
Response: {
  "user_id": 1,
  "preferred_hour": 9,
  "preferred_days": "1,2,3,4,5",
  "quiet_hours_start": 22,
  "quiet_hours_end": 7,
  "auto_optimize": true,
  "min_interval_hours": 4,
  "max_reminders_per_day": 5
}
```

### Update Preferences
```
PUT /smart-reminders/preferences
Body: { "preferred_hour": 14, "auto_optimize": false }
Response: { ... updated preferences ... }
```

### Get Optimal Time
```
GET /smart-reminders/optimal-time
Response: {
  "optimal_hour": 10,
  "confidence": 0.85,
  "method": "activity_analysis",
  "is_quiet_hour": false,
  "alternative_hours": [14, 16, 9]
}
```

Methods:
- `user_preference` — auto_optimize disabled, uses configured preferred_hour
- `default_insufficient_data` — fewer than 5 activities logged
- `activity_analysis` — ML-based analysis of user engagement patterns
- `fallback_all_quiet` — all active hours fall within quiet period

### Get Optimal Days
```
GET /smart-reminders/optimal-days
Response: {
  "optimal_days": [1, 3, 5],
  "confidence": 0.78,
  "method": "activity_analysis",
  "day_scores": { "0": 0.4, "1": 1.0, "2": 0.2, ... }
}
```

### Should Send Reminder
```
GET /smart-reminders/should-send?hour=10
Response: {
  "should_send": true,
  "reason": "optimal_window",
  "current_hour": 10,
  "optimal_hour": 10,
  "confidence": 0.85
}
```

Reasons: `quiet_hours`, `optimal_window`, `outside_optimal_window`

## Optimization Algorithm

1. Collect activity events (app opens, expense entries, bill payments)
2. Build hourly/daily frequency distributions using Counter
3. Score each non-quiet hour by normalized activity count
4. Return highest scoring hour with confidence = min(score + 0.3, 1.0)
5. For days, return all days with normalized score > 0.3
6. Should-send check allows ±1 hour window around optimal time

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_smart_reminder.py -v
```

36 tests covering unit helpers, service logic, and route integration.
