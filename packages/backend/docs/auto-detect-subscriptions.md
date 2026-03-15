# Auto-Detect Subscriptions from Recurring Charges

## Overview

Automatically identifies subscription services by analyzing recurring transaction patterns in a user's expense history. Uses pattern matching, cadence detection, and confidence scoring to surface hidden subscriptions and calculate their true monthly cost.

## Features

- **Smart Pattern Detection**: Analyzes expense notes/descriptions to group recurring charges by merchant
- **Merchant Name Normalization**: Strips payment prefixes, date suffixes, and reference numbers for accurate matching
- **Cadence Detection**: Identifies weekly, biweekly, monthly, quarterly, and yearly subscription patterns
- **Confidence Scoring**: Multi-factor scoring based on occurrence count, amount consistency, interval regularity, and known service matching
- **Known Service Database**: Pre-loaded with 40+ popular subscription services for immediate recognition
- **Monthly Cost Summary**: Normalizes all subscriptions to monthly equivalents for total cost visibility
- **User Controls**: Confirm or dismiss detected subscriptions

## API Endpoints

### POST `/subscriptions/scan`
Trigger a subscription detection scan on the user's expense history.

**Response:**
```json
{
  "detected_count": 3,
  "subscriptions": [
    {
      "id": 1,
      "merchant_name": "Netflix",
      "normalized_name": "netflix",
      "amount": 15.99,
      "currency": "INR",
      "cadence": "MONTHLY",
      "confidence": 0.92,
      "first_seen": "2024-01-15",
      "last_seen": "2024-06-15",
      "next_expected": "2024-07-15",
      "occurrence_count": 6,
      "status": "detected",
      "is_active": true
    }
  ]
}
```

### GET `/subscriptions`
List all detected subscriptions.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `active_only` | bool | `true` | Filter to active subscriptions only |

### GET `/subscriptions/summary`
Get monthly/yearly subscription cost summary.

**Response:**
```json
{
  "monthly_total": 134.23,
  "yearly_total": 1610.76,
  "subscription_count": 3,
  "subscriptions": [
    {
      "id": 1,
      "name": "Netflix",
      "amount": 15.99,
      "cadence": "MONTHLY",
      "monthly_equivalent": 15.99,
      "confidence": 0.92
    }
  ]
}
```

### GET `/subscriptions/<id>`
Get details of a specific detected subscription.

### PATCH `/subscriptions/<id>/status`
Update subscription status.

**Body:**
```json
{
  "status": "confirmed"  // or "dismissed", "detected"
}
```

## Detection Algorithm

### 1. Merchant Grouping
Expenses are grouped by normalized merchant name:
- Payment prefixes removed (e.g., "Payment to Netflix" → "netflix")
- Date suffixes removed (e.g., "Spotify Jan 2024" → "spotify")
- Reference numbers stripped
- Whitespace collapsed and lowercased

### 2. Cadence Analysis
For each merchant group with 2+ transactions:
- Calculate intervals between consecutive charges
- Match average interval to cadence buckets (weekly: 5-9 days, monthly: 25-35 days, etc.)
- Score regularity based on deviation from expected interval

### 3. Confidence Scoring
Weighted combination of four factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| Occurrence | 25% | Logarithmic scale, caps at ~12 occurrences |
| Amount Consistency | 30% | How similar each charge amount is |
| Interval Regularity | 30% | How consistent the time between charges |
| Known Service | 15% | Bonus for matching 40+ known subscription services |

Minimum confidence threshold: 0.3 (or any confidence if known service).

### 4. Cost Normalization
Monthly equivalents for cost summary:

| Cadence | Multiplier |
|---------|------------|
| Weekly | × 4.33 |
| Biweekly | × 2.17 |
| Monthly | × 1.00 |
| Quarterly | × 0.33 |
| Yearly | × 0.083 |

## Data Model

### `detected_subscriptions` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `user_id` | INTEGER | Foreign key to users |
| `merchant_name` | VARCHAR(255) | Original merchant name |
| `normalized_name` | VARCHAR(255) | Normalized for matching |
| `amount` | NUMERIC(12,2) | Average charge amount |
| `currency` | VARCHAR(10) | Currency code |
| `cadence` | VARCHAR(20) | Detected cadence |
| `confidence` | NUMERIC(5,4) | Confidence score 0-1 |
| `first_seen` | DATE | First detected charge |
| `last_seen` | DATE | Most recent charge |
| `next_expected` | DATE | Predicted next charge |
| `occurrence_count` | INTEGER | Number of matching charges |
| `status` | VARCHAR(20) | detected/confirmed/dismissed |
| `linked_recurring_id` | INTEGER | Optional link to recurring_expenses |
| `category_id` | INTEGER | Optional category |
| `is_active` | BOOLEAN | Active flag |

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_subscriptions.py -v
```

24 tests covering:
- Merchant name normalization (9 edge cases)
- Cadence detection (4 patterns)
- Amount consistency scoring
- Known service identification
- Confidence computation
- Full detection pipeline (5 integration tests)
- Status management (4 tests)
- Subscription listing (2 tests)
- Monthly cost calculation (2 tests)
- API endpoints (9 tests including auth)
