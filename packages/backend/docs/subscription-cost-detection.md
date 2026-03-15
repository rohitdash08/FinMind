# Subscription Cost Increase Detection

## Overview

Monitors subscription plan pricing and automatically notifies affected users when their subscription costs increase. Tracks price history, generates alerts, and provides cost analysis.

## Database Tables

### `subscription_price_history`
| Column | Type | Description |
|---|---|---|
| id | SERIAL PK | Auto-increment ID |
| plan_id | INTEGER FK | References subscription_plans(id) |
| old_price_cents | INTEGER | Previous price in cents |
| new_price_cents | INTEGER | New price in cents |
| change_pct | NUMERIC(8,2) | Percentage change |
| detected_at | TIMESTAMP | When change was detected |
| notified | BOOLEAN | Whether notifications were sent |

### `subscription_cost_alerts`
| Column | Type | Description |
|---|---|---|
| id | SERIAL PK | Auto-increment ID |
| user_id | INTEGER FK | References users(id) |
| plan_id | INTEGER FK | References subscription_plans(id) |
| old_price_cents | INTEGER | Previous price |
| new_price_cents | INTEGER | New price |
| change_pct | NUMERIC(8,2) | Percentage increase |
| acknowledged | BOOLEAN | User acknowledged the alert |
| created_at | TIMESTAMP | When alert was created |

## API Endpoints

All endpoints require JWT authentication.

### Update Plan Price
```
PUT /subscriptions/plans/:plan_id/price
Body: { "price_cents": 1499 }
Response: {
  "plan_id": 1,
  "changed": true,
  "old_price_cents": 999,
  "new_price_cents": 1499,
  "change_pct": 50.05,
  "direction": "increase",
  "alerts_created": 3
}
```

### Get Price History
```
GET /subscriptions/plans/:plan_id/price-history?limit=20
Response: [
  {
    "id": 1,
    "plan_id": 1,
    "old_price_cents": 999,
    "new_price_cents": 1499,
    "change_pct": 50.05,
    "detected_at": "2024-01-15T10:30:00",
    "notified": false
  }
]
```

### Get All Price Changes
```
GET /subscriptions/price-changes?limit=50
```

### Get User Alerts
```
GET /subscriptions/alerts?unacknowledged=true
Response: [
  {
    "id": 1,
    "user_id": 1,
    "plan_id": 1,
    "old_price_cents": 999,
    "new_price_cents": 1499,
    "change_pct": 50.05,
    "acknowledged": false,
    "created_at": "2024-01-15T10:30:00"
  }
]
```

### Acknowledge Alert
```
POST /subscriptions/alerts/:alert_id/acknowledge
```

### Acknowledge All Alerts
```
POST /subscriptions/alerts/acknowledge-all
Response: { "acknowledged_count": 5 }
```

### Cost Summary
```
GET /subscriptions/summary
Response: {
  "total_monthly_cents": 2999,
  "subscription_count": 3,
  "plans": [
    { "plan_id": 1, "name": "Pro", "price_cents": 999, "interval": "monthly" }
  ],
  "recent_increases": [ ... ]
}
```

Monthly normalization: yearly plans ÷ 12, weekly plans × 4.

### Detect Increases
```
GET /subscriptions/increases?plan_id=1
Response: [
  {
    "plan_id": 1,
    "old_price_cents": 999,
    "new_price_cents": 1499,
    "change_pct": 50.05,
    "affected_users": 42
  }
]
```

## How It Works

1. When a plan price is updated via `PUT /subscriptions/plans/:id/price`:
   - Price history record is created
   - If price **increased**, alerts are generated for all **active** subscribers
   - Inactive subscribers are not alerted
2. Users can view and acknowledge alerts
3. Cost summary normalizes all intervals to monthly for comparison
4. Decrease detection records history but does not create alerts

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_subscription_cost.py -v
```

38 tests covering service logic and route integration.
