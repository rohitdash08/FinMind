# Spending Trend Heatmap Visualization

## Overview

Provides multiple heatmap views of spending data for rich visual analytics. Supports daily (GitHub contribution-style), weekly aggregate, hourly activity grid, and per-category breakdowns — all with normalized intensity values ready for frontend rendering.

## API Endpoints

All endpoints require JWT authentication.

### GET /heatmap/daily

Daily spending heatmap (GitHub contribution-style).

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 365 | Number of days to include |
| category_id | int | null | Filter by category |

**Response:**
```json
{
  "days": [
    {
      "date": "2025-03-14",
      "amount": 150.00,
      "count": 3,
      "intensity": 0.75,
      "day_of_week": 4
    }
  ],
  "total_days": 365,
  "active_days": 42,
  "total_spending": 5200.00,
  "max_daily_amount": 200.00
}
```

### GET /heatmap/weekly

Weekly aggregated spending heatmap.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| weeks | int | 52 | Number of weeks to include |
| category_id | int | null | Filter by category |

**Response:**
```json
{
  "weeks": [
    {
      "year": 2025,
      "week": 11,
      "week_start": "2025-03-10",
      "amount": 450.00,
      "count": 8,
      "intensity": 0.6
    }
  ],
  "total_weeks": 52,
  "total_spending": 18000.00,
  "max_weekly_amount": 750.00
}
```

### GET /heatmap/hourly

7×24 hour-of-day × day-of-week activity grid.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 30 | Number of days of data |
| category_id | int | null | Filter by category |

**Response:**
```json
{
  "cells": [
    {
      "day_of_week": 0,
      "hour": 12,
      "amount": 320.00,
      "count": 5,
      "intensity": 0.8
    }
  ],
  "max_amount": 400.00,
  "total_spending": 5200.00
}
```

The `cells` array contains 168 entries (7 days × 24 hours).

### GET /heatmap/categories

Per-category spending breakdown with intensity.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 30 | Period to analyze |

**Response:**
```json
{
  "categories": [
    {
      "category_id": 1,
      "category_name": "Food",
      "amount": 800.00,
      "count": 15,
      "intensity": 1.0,
      "percentage": 40.0
    }
  ],
  "total_spending": 2000.00,
  "total_categories": 3
}
```

### GET /heatmap/summary

Overall heatmap summary statistics.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 365 | Period to summarize |

**Response:**
```json
{
  "total_spending": 18500.00,
  "total_transactions": 245,
  "total_days": 365,
  "active_days": 180,
  "activity_rate": 49.3,
  "average_daily_spending": 50.68,
  "max_daily_spending": 450.00,
  "max_single_transaction": 350.00,
  "busiest_day": "2025-01-15",
  "busiest_day_amount": 450.00
}
```

## Intensity Values

All heatmap endpoints return `intensity` fields normalized between 0.0 and 1.0:

- **0.0** — No spending
- **1.0** — Maximum spending in the dataset

This normalization allows frontends to directly map intensity to color scales (e.g., green shades for a GitHub-style heatmap).

## Architecture

- **Service:** `app/services/spending_heatmap.py` — Pure analytics over existing Expense table; no new database tables required.
- **Routes:** `app/routes/spending_heatmap.py` — REST endpoints under `/heatmap` prefix.
- **Tests:** `tests/test_spending_heatmap.py` — 23 tests covering all service functions and routes.

## Usage Notes

- The `spent_at` field on Expense is a Date type, so hourly heatmap defaults transactions to 12:00 PM.
- Uncategorized expenses appear as "Uncategorized" in category heatmap.
- All monetary amounts use the raw numeric value from the database.
