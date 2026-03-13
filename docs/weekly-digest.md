# Weekly Financial Digest

FinMind generates weekly financial summaries highlighting spending trends,
category breakdowns, anomalies, and actionable insights.

## Features

- **Spending summary**: Total expenses, income, net flow, transaction count
- **Week-over-week comparison**: Percentage change vs previous week
- **Category breakdown**: Top spending categories with percentages
- **Daily spending chart data**: Per-day totals for visualization
- **Anomaly detection**: Flags spending spikes, drops, and large transactions
- **Upcoming bills**: Bills due in the next 7 days
- **AI-enhanced narrative** (optional): Gemini-powered summary and tips
- **Heuristic fallback**: Smart tips generated without AI when Gemini is unavailable
- **Email rendering**: Plain-text email template for digest delivery
- **Automated delivery**: Weekly cron job sends digests every Monday at 9:00 AM UTC

## API Endpoints

### `GET /digest/weekly`

Generate a weekly digest for the authenticated user.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `week_of` | ISO date | Previous week | Any date within the target week |

**Headers (optional):**
| Header | Description |
|--------|-------------|
| `X-Gemini-Api-Key` | Gemini API key for AI narrative |
| `X-Insight-Persona` | Custom AI persona |

**Response:**
```json
{
  "week_start": "2026-03-09",
  "week_end": "2026-03-15",
  "total_expenses": 1500.00,
  "total_income": 2000.00,
  "net_flow": 500.00,
  "previous_week_expenses": 1200.00,
  "week_over_week_change_pct": 25.0,
  "transaction_count": 15,
  "daily_spending": [
    {"date": "2026-03-09", "total": 200.00},
    {"date": "2026-03-10", "total": 350.00},
    ...
  ],
  "category_breakdown": [
    {"category": "Food", "total": 800.00, "count": 8, "pct": 53.3},
    {"category": "Transport", "total": 700.00, "count": 7, "pct": 46.7}
  ],
  "anomalies": ["Spending jumped 25% vs last week"],
  "upcoming_bills": [
    {"id": 1, "name": "Rent", "amount": 15000.00, "due_date": "2026-03-20", "autopay": true}
  ],
  "tips": ["Your biggest category was Food..."],
  "method": "heuristic"
}
```

### `GET /digest/weekly/email-preview`

Same as `/digest/weekly` but also returns a formatted plain-text email body.

```json
{
  "email_body": "📊 FinMind Weekly Digest...",
  "digest": { ... }
}
```

## Anomaly Detection

The system flags:
- **Spending spike**: >30% increase week-over-week
- **Spending drop**: >20% decrease (positive reinforcement)
- **Large transaction**: Single transaction >40% of weekly total
- **No data**: Zero expenses recorded (potential tracking gap)

## Automated Delivery

Digests are sent automatically every **Monday at 9:00 AM UTC** via the
background job manager. The job:

1. Iterates all users
2. Generates each user's digest for the previous week
3. Renders to email format
4. Sends via the configured SMTP provider
5. Retries up to 3 times on failure (60s → 600s backoff)

Monitor via `GET /jobs/health` or `GET /jobs/status` (admin).

## AI Enhancement

When a Gemini API key is available (per-user header or server config),
the digest includes:

- `narrative`: 2-3 sentence AI-written summary
- `ai_tips`: 3 actionable AI-generated tips
- `mood`: Overall financial health (great/good/okay/concerning/critical)

Falls back to heuristic tips transparently if Gemini is unavailable.
