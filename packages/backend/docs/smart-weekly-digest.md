# Smart Weekly Financial Digest

Automated weekly summaries highlighting spending trends, category analysis, and actionable insights.

## Overview

The digest analyses the past 7 days of user activity and compares it against the prior week to surface trends. Each digest includes:

- **Summary metrics** with week-over-week percentage changes
- **Top spending categories** ranked by amount with share percentages
- **Largest individual transactions** for quick anomaly review
- **Upcoming bills** due in the next 7 days
- **Smart insights** – auto-generated, contextual financial tips

## API Endpoints

### Get Weekly Digest

```
GET /digest/weekly
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| date | YYYY-MM-DD | today | Anchor date (last day of reporting week) |

**Response** `200`:
```json
{
  "digest": {
    "period": { "start": "2025-01-08", "end": "2025-01-14" },
    "summary": {
      "total_income": 3000.00,
      "total_expenses": 1200.00,
      "net_savings": 1800.00,
      "transaction_count": 15,
      "previous_week": {
        "total_income": 2500.00,
        "total_expenses": 900.00,
        "net_savings": 1600.00,
        "transaction_count": 12
      },
      "change": {
        "income_pct": 20.0,
        "expenses_pct": 33.3,
        "savings_pct": 12.5,
        "transaction_count_pct": 25.0
      }
    },
    "top_categories": [
      {
        "category_id": 1,
        "category_name": "Rent",
        "amount": 600.00,
        "transaction_count": 1,
        "share_pct": 50.0
      }
    ],
    "largest_transactions": [
      {
        "id": 42,
        "amount": 600.00,
        "type": "EXPENSE",
        "notes": "Monthly rent",
        "date": "2025-01-10",
        "currency": "INR"
      }
    ],
    "upcoming_bills": [
      {
        "id": 5,
        "name": "Electricity",
        "amount": 150.00,
        "currency": "INR",
        "due_date": "2025-01-18",
        "autopay": false
      }
    ],
    "insights": [
      {
        "type": "warning",
        "title": "Spending Spike",
        "message": "Your expenses increased 33.3% compared to last week..."
      },
      {
        "type": "positive",
        "title": "Positive Cash Flow",
        "message": "You saved 1800.00 this week..."
      }
    ],
    "generated_at": "2025-01-14T12:00:00"
  }
}
```

### Digest History

```
GET /digest/weekly/history
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| weeks | int | 4 | Number of past weeks (max 12) |

Returns summary metrics for each week to populate trend charts.

## Insight Types

| Type | Trigger | Title |
|------|---------|-------|
| `warning` | Expenses up >20% vs last week | Spending Spike |
| `positive` | Expenses down >10% vs last week | Great Savings Week |
| `positive` | Income > Expenses | Positive Cash Flow |
| `warning` | Expenses > Income | Negative Cash Flow |
| `info` | Top category >50% of spend | Category Dominance |
| `info` | Bills due in next 7 days | Bills Due Soon |
| `info` | Zero transactions this week | No Activity |

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_digest.py -v
```

14 tests covering digest generation, week-over-week comparison, category ranking, transaction sorting, bill detection, insight triggers, date parameters, history, and auth.

## Files

| File | Description |
|------|-------------|
| `app/services/digest.py` | Digest generation engine and insight derivation |
| `app/routes/digest.py` | REST endpoints (weekly digest + history) |
| `app/routes/__init__.py` | Blueprint registration |
| `tests/test_digest.py` | 14 comprehensive tests |
| `docs/smart-weekly-digest.md` | This documentation |
