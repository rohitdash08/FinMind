# Category Overspend Early Warning System

## Overview

Alerts users before they exceed their budget limits by monitoring spending per category against configurable thresholds. Provides real-time status, proactive alerts, and end-of-month spending forecasts.

## Features

- **Budget Management**: Set monthly limits per category with custom warning/critical thresholds
- **Real-time Status**: Check current spending against all active budgets
- **Alert Levels**: Normal → Warning (80%) → Critical (95%) → Exceeded (100%)
- **Smart Alerts**: De-duplicated alerts generated per period per alert type
- **Spending Forecast**: Projects end-of-month spending based on current daily rate
- **Daily Safe Spend**: Calculates how much you can safely spend per remaining day
- **Alert Management**: Read/unread tracking with bulk mark-as-read

## API Endpoints

### Budget CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/budgets` | Create a category budget |
| GET | `/budgets` | List all budgets |
| GET | `/budgets/<id>` | Get budget details |
| PATCH | `/budgets/<id>` | Update budget settings |
| DELETE | `/budgets/<id>` | Deactivate budget |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/budgets/status` | Check spending vs all budgets |
| GET | `/budgets/forecast` | End-of-month spending forecast |

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/budgets/alerts/generate` | Generate new alerts |
| GET | `/budgets/alerts` | List alerts |
| PATCH | `/budgets/alerts/<id>/read` | Mark alert as read |
| POST | `/budgets/alerts/read-all` | Mark all alerts read |

## Create Budget

```http
POST /budgets
Content-Type: application/json
Authorization: Bearer <token>

{
  "category_id": 1,
  "monthly_limit": 5000.00,
  "warning_threshold": 80.0,
  "critical_threshold": 95.0
}
```

## Budget Status Response

```json
[
  {
    "budget_id": 1,
    "category_id": 1,
    "category_name": "Food",
    "monthly_limit": 5000.0,
    "spent": 4200.0,
    "remaining": 800.0,
    "percentage_used": 84.0,
    "alert_level": "warning",
    "daily_safe_spend": 80.0,
    "days_remaining": 10,
    "period_start": "2024-06-01",
    "period_end": "2024-06-30",
    "currency": "INR"
  }
]
```

## Spending Forecast Response

```json
[
  {
    "budget_id": 1,
    "category_name": "Food",
    "current_spent": 4200.0,
    "monthly_limit": 5000.0,
    "projected_total": 6300.0,
    "projected_percentage": 126.0,
    "daily_rate": 210.0,
    "will_exceed": true,
    "projected_overspend": 1300.0,
    "days_remaining": 10,
    "currency": "INR"
  }
]
```

## Alert Levels

| Level | Trigger | Description |
|-------|---------|-------------|
| `normal` | < warning_threshold | Spending within safe limits |
| `warning` | ≥ warning_threshold | Approaching budget limit |
| `critical` | ≥ critical_threshold | Very close to exceeding |
| `exceeded` | ≥ 100% | Budget limit exceeded |

## Data Model

### `category_budgets` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `user_id` | INTEGER | Foreign key to users |
| `category_id` | INTEGER | Foreign key to categories |
| `monthly_limit` | NUMERIC(12,2) | Monthly budget limit |
| `currency` | VARCHAR(10) | Currency code |
| `warning_threshold` | NUMERIC(5,2) | Warning % (default 80) |
| `critical_threshold` | NUMERIC(5,2) | Critical % (default 95) |
| `is_active` | BOOLEAN | Active flag |

### `overspend_alerts` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `user_id` | INTEGER | Foreign key to users |
| `category_id` | INTEGER | Foreign key to categories |
| `budget_id` | INTEGER | Foreign key to category_budgets |
| `alert_type` | VARCHAR(20) | warning/critical/exceeded |
| `spent_amount` | NUMERIC(12,2) | Amount spent when alert fired |
| `budget_limit` | NUMERIC(12,2) | Budget limit at alert time |
| `percentage_used` | NUMERIC(6,2) | Percentage of budget used |
| `period_start` | DATE | Budget period start |
| `period_end` | DATE | Budget period end |
| `is_read` | BOOLEAN | Read status |

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_budgets.py -v
```

Comprehensive coverage with unit, integration, and API tests.
