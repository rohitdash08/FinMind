# Event-Driven Financial Activity System

Issue: [#97](https://github.com/rohitdash08/FinMind/issues/97)

## Overview

Append-only event log for all financial activity. Enables event sourcing,
audit trails, activity replay, analytics, and subscription-based notifications.

## Event Types

| Event | Description |
|-------|-------------|
| `expense.created` | New expense recorded |
| `expense.updated` | Expense modified |
| `expense.deleted` | Expense removed |
| `bill.created` | New bill added |
| `bill.paid` | Bill marked as paid |
| `bill.overdue` | Bill past due date |
| `bill.updated` | Bill modified |
| `bill.deleted` | Bill removed |
| `budget.exceeded` | Spending exceeds budget |
| `budget.warning` | Spending approaching limit |
| `category.created` | New category created |
| `category.deleted` | Category removed |
| `anomaly.detected` | Unusual activity detected |
| `account.login` | Successful login |
| `account.settings_changed` | Settings updated |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/emit` | Emit a financial event |
| GET | `/events` | List events (filtered, paginated) |
| GET | `/events/<id>` | Get single event |
| GET | `/events/replay` | Replay in chronological order |
| GET | `/events/stats` | Event analytics |
| GET | `/events/types` | List available event types |
| POST | `/events/subscribe` | Subscribe to event type |
| DELETE | `/events/subscribe/<id>` | Unsubscribe |
| GET | `/events/subscriptions` | List subscriptions |

## Data Model

### `financial_events` (append-only)
- `event_type` — dotted notation (e.g., `expense.created`)
- `entity_type` — resource type (expense, bill, category, etc.)
- `entity_id` — ID of the affected resource
- `payload` — JSON event data
- `metadata` — JSON contextual data (source, IP, etc.)

### `event_subscriptions`
- Per-user subscription to event types
- Supports `internal` and `webhook` callback types
- Unique constraint prevents duplicate subscriptions

## Key Features

1. **Append-Only Log** — Events are immutable once written
2. **Rich Filtering** — By event type, entity type, time range
3. **Event Replay** — Chronological playback for any entity
4. **Analytics** — Activity stats by type, entity, and daily breakdowns
5. **Subscriptions** — Subscribe to specific event types
6. **Convenience Emitters** — Pre-built functions for common events
7. **Idempotent Subscriptions** — Re-subscribing reactivates existing

## Testing

24 tests covering:
- Event emission (5 tests)
- Event listing & filtering (7 tests)
- Event replay (3 tests)
- Event statistics (2 tests)
- Event types listing (1 test)
- Subscriptions lifecycle (6 tests)
