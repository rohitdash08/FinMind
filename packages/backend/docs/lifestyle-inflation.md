# Lifestyle Inflation Detection Insights

Detect rising lifestyle expenses over time by analyzing spending trends and flagging significant increases.

## Overview

- **Monthly trend analysis** — Track spending over customizable time periods
- **Spending spike alerts** — Flag months with ≥10% increase over previous
- **Category inflation** — Detect per-category spending increases ≥20%
- **Spending snapshots** — Point-in-time spending breakdowns by category
- **Severity levels** — Moderate (10-25%) and high (25%+) alerts

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/inflation/snapshot` | Generate spending snapshot |
| POST | `/inflation/detect` | Run inflation detection |
| GET | `/inflation/trends` | Monthly spending trends |
| GET | `/inflation/alerts` | List inflation alerts |
| POST | `/inflation/alerts/<id>/acknowledge` | Acknowledge alert |
| GET | `/inflation/summary` | Inflation analysis summary |

## Architecture

| Component | File |
|-----------|------|
| Migration | `app/db/036_lifestyle_inflation.sql` |
| Models | `app/models.py` → `LifestyleSnapshot`, `InflationAlert` |
| Service | `app/services/lifestyle_inflation.py` |
| Routes | `app/routes/lifestyle_inflation.py` |
| Tests | `tests/test_lifestyle_inflation.py` |

## Testing

```bash
python -m pytest tests/test_lifestyle_inflation.py -v
# 27 tests covering snapshots, detection, trends, alerts, and routes
```
