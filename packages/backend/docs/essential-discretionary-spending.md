# Essential vs Discretionary Spending Breakdown

## Overview

Classify spending categories as essential or discretionary to highlight
financial priorities and provide actionable insights into spending patterns.

Resolves: [#120](https://github.com/rohitdash08/FinMind/issues/120)

## Features

- **Auto-classification** — Automatic categorization using keyword matching against 60+ known patterns
- **Manual override** — Users can reclassify any category
- **Spending breakdown** — Detailed analysis with totals, percentages, and per-category details
- **Trend analysis** — Monthly essential vs discretionary trend over configurable periods
- **Smart insights** — Generated insights based on spending ratios

## Classification Logic

Categories are classified based on keyword matching:

**Essential** (necessities):
- Housing: rent, mortgage
- Utilities: electric, water, gas, internet, phone
- Food: groceries
- Health: healthcare, medical, pharmacy, insurance
- Transport: fuel, commute, transit
- Education: tuition, childcare
- Debt: loan, minimum payment, taxes

**Discretionary** (wants):
- Food out: dining, restaurant, takeout, fast food, coffee
- Entertainment: movies, streaming, gaming
- Shopping: clothing, fashion, electronics
- Travel: vacation, hotel, flights
- Personal: gym, spa, beauty, hobbies
- Social: bar, alcohol, gifts

## API Endpoints

### `POST /spending/auto-classify`

Auto-classify all unclassified categories using keyword matching.

**Response:**
```json
{
  "classified": {
    "essential": 3,
    "discretionary": 5,
    "unclassified": 2
  }
}
```

### `PUT /spending/categories/<id>`

Manually set spending class for a category.

**Body:**
```json
{
  "spending_class": "ESSENTIAL"  // or "DISCRETIONARY", "UNCLASSIFIED"
}
```

### `GET /spending/categories`

Get all categories grouped by spending class.

**Response:**
```json
{
  "essential": [{"id": 1, "name": "Groceries", "spending_class": "ESSENTIAL"}],
  "discretionary": [{"id": 2, "name": "Entertainment", "spending_class": "DISCRETIONARY"}],
  "unclassified": []
}
```

### `GET /spending/breakdown`

Get essential vs discretionary spending breakdown.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| start_date | string | 30 days ago | Start date (YYYY-MM-DD) |
| end_date | string | today | End date (YYYY-MM-DD) |

**Response:**
```json
{
  "period": {"start": "2024-06-01", "end": "2024-06-30"},
  "totals": {
    "grand_total": 2500.00,
    "essential": 1800.00,
    "discretionary": 600.00,
    "unclassified": 100.00
  },
  "percentages": {
    "essential": 72.0,
    "discretionary": 24.0,
    "unclassified": 4.0
  },
  "categories": {
    "essential": [{"name": "Rent", "amount": 1200.00, "count": 1, "percentage": 48.0}],
    "discretionary": [{"name": "Dining Out", "amount": 350.00, "count": 8, "percentage": 14.0}],
    "unclassified": []
  },
  "insights": [
    "Essential spending is 72% of total. You have a healthy balance between needs and wants.",
    "Essential-to-discretionary ratio: 3.0:1"
  ]
}
```

### `GET /spending/trend`

Get monthly spending trend by class.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| months | integer | 6 | Number of months (1-24) |

**Response:**
```json
{
  "trend": [
    {"month": "2024-01", "essential": 1800, "discretionary": 500, "total": 2300, "essential_pct": 78.3, "discretionary_pct": 21.7},
    {"month": "2024-02", "essential": 1750, "discretionary": 600, "total": 2350, "essential_pct": 74.5, "discretionary_pct": 25.5}
  ]
}
```

## Database Changes

- Added `spending_class` column to `categories` table (VARCHAR(20), default: 'UNCLASSIFIED')
- Migration: `app/db/027_spending_classification.sql`
- Model: `SpendingClass` enum added to `models.py`

## Technical Details

- No external dependencies required
- Uses existing category and expense tables
- Auto-classification is idempotent (only classifies UNCLASSIFIED categories)
- Manual classification always overrides auto-classification
- Insights are generated dynamically based on spending ratios
