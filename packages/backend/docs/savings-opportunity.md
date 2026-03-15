# Savings Opportunity Detection Engine

Automatically analyze spending patterns to identify where users can reduce spending and save money.

## Overview

- **Spending spike detection** — Flag categories with spending significantly above historical average
- **Category overspend detection** — Identify categories consuming disproportionate share of total spending
- **Confidence scoring** — Each opportunity rated by detection confidence
- **Actionable management** — Dismiss, act on, and track savings opportunities

## Detection Algorithms

### Spending Spikes
Compares recent spending (last N days) against historical average (3x period). Flags categories where current spending exceeds `threshold × average` (default 1.5x).

### Category Overspend
Identifies categories consuming more than 40% of total spending. Suggests reducing to 30% as a target.

## API Endpoints

All endpoints require JWT authentication.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/savings/detect` | Run detection algorithms |
| GET | `/savings` | List saved opportunities |
| GET | `/savings/<id>` | Get opportunity detail |
| POST | `/savings/<id>/dismiss` | Dismiss opportunity |
| POST | `/savings/<id>/act` | Mark action taken |
| GET | `/savings/summary` | Savings summary & stats |

### Run Detection

```http
POST /savings/detect
{"days": 30}
```

### List Opportunities

```http
GET /savings?type=spending_spike&status=active&limit=20
```

### Summary

```http
GET /savings/summary
```

Returns total potential savings, acted count, breakdown by type.

## Architecture

| Component | File |
|-----------|------|
| Migration | `app/db/035_savings_opportunity.sql` |
| Model | `app/models.py` → `SavingsOpportunity` |
| Service | `app/services/savings_opportunity.py` |
| Routes | `app/routes/savings_opportunity.py` |
| Tests | `tests/test_savings_opportunity.py` |

## Testing

```bash
python -m pytest tests/test_savings_opportunity.py -v
# 29 tests covering detection algorithms, CRUD operations, and route integration
```
