# Recurring Transaction Anomaly Alerts

## Overview

Monitors recurring expenses for unexpected amount changes. Compares actual charges against historical snapshots and generates alerts when deviations exceed configurable thresholds (default: 10%).

## Database Tables

### `recurring_expense_snapshots`
| Column | Type | Description |
|---|---|---|
| id | SERIAL PK | Auto-increment ID |
| recurring_id | INTEGER FK | References recurring_expenses(id) |
| amount | NUMERIC(12,2) | Recorded amount |
| recorded_at | TIMESTAMP | When snapshot was taken |

### `recurring_anomaly_alerts`
| Column | Type | Description |
|---|---|---|
| id | SERIAL PK | Auto-increment ID |
| user_id | INTEGER FK | References users(id) |
| recurring_id | INTEGER FK | References recurring_expenses(id) |
| expected_amount | NUMERIC(12,2) | Expected amount |
| actual_amount | NUMERIC(12,2) | Actual amount charged |
| deviation_pct | NUMERIC(8,2) | Percentage deviation |
| alert_type | VARCHAR(30) | amount_increase or amount_decrease |
| acknowledged | BOOLEAN | User acknowledged |
| created_at | TIMESTAMP | When alert was created |

## API Endpoints

All endpoints require JWT authentication.

### Check Single Transaction
```
POST /recurring-anomalies/check
Body: { "recurring_id": 1, "amount": 150.00, "threshold_pct": 10.0 }
Response: {
  "recurring_id": 1,
  "expected_amount": 100.0,
  "actual_amount": 150.0,
  "deviation_pct": 50.0,
  "threshold_pct": 10.0,
  "is_anomaly": true,
  "alert_id": 1,
  "alert_type": "amount_increase"
}
```

### Scan All Recurring Expenses
```
POST /recurring-anomalies/scan
Body: { "threshold_pct": 10.0 }
Response: {
  "total_checked": 5,
  "anomalies_found": 1,
  "anomalies": [ ... ],
  "threshold_pct": 10.0
}
```

### Get Alerts
```
GET /recurring-anomalies/alerts?unacknowledged=true
```

### Acknowledge Alert
```
POST /recurring-anomalies/alerts/:id/acknowledge
```

### Acknowledge All
```
POST /recurring-anomalies/alerts/acknowledge-all
Response: { "acknowledged_count": 3 }
```

### Anomaly Summary
```
GET /recurring-anomalies/summary
Response: {
  "total_alerts": 5,
  "unacknowledged": 2,
  "by_type": { "amount_increase": 3, "amount_decrease": 2 },
  "avg_deviation_pct": 35.5,
  "max_deviation_pct": 100.0
}
```

### Get Snapshots
```
GET /recurring-anomalies/snapshots/:recurring_id?limit=20
```

## Detection Algorithm

1. Expected amount = most recent snapshot, or recurring expense's configured amount
2. Deviation = |actual - expected| / expected × 100
3. If deviation > threshold (default 10%), create alert
4. Each check records a new snapshot for future comparisons
5. Scan compares current recurring amount vs latest snapshot

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_recurring_anomaly.py -v
```

33 tests covering snapshots, anomaly detection, scanning, alerts, and routes.
