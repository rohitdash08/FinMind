# FinMind Webhook Event System

## Overview

FinMind supports webhook subscriptions so integrations can receive real-time
notifications when key events happen in a user's account.

## Authentication

All webhook management endpoints require a valid JWT access token in the
`Authorization: Bearer <token>` header.

## Webhook Registration

```
POST /webhooks
```

**Request body:**
```json
{
  "url": "https://your-server.com/finmind-events",
  "events": ["expense.created", "expense.deleted"],
  "secret": "optional-custom-secret"
}
```

- `url` (required) — HTTPS endpoint that will receive events
- `events` (optional) — Array of event types to subscribe to. Defaults to `["*"]` (all events)
- `secret` (optional) — Custom signing secret. If omitted, a 32-byte hex secret is auto-generated

**Response (201):**
```json
{
  "id": 1,
  "url": "https://your-server.com/finmind-events",
  "events": ["expense.created", "expense.deleted"],
  "active": true,
  "failure_count": 0,
  "secret": "a1b2c3...",
  "created_at": "2026-02-15T12:00:00",
  "updated_at": "2026-02-15T12:00:00"
}
```

> **Note:** The `secret` is only returned on creation. Store it securely.

## Signed Delivery

Every webhook delivery includes an HMAC-SHA256 signature for payload verification.

### Headers

| Header | Description |
|--------|-------------|
| `X-FinMind-Signature` | `sha256=<hex-digest>` — HMAC-SHA256 of the raw request body |
| `X-FinMind-Delivery` | UUID identifying this specific delivery attempt |
| `X-FinMind-Event` | The event type (e.g., `expense.created`) |
| `Content-Type` | `application/json` |

### Verifying Signatures

```python
import hmac
import hashlib

def verify(secret: str, payload: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Event Types

| Event | Trigger | Payload |
|-------|---------|---------|
| `expense.created` | New expense added | `{id, amount, currency, category_id, description, date}` |
| `expense.updated` | Expense modified | `{id, amount, currency, category_id, description, date}` |
| `expense.deleted` | Expense removed | `{id, amount, currency, category_id, description, date}` |
| `bill.created` | New bill added | `{id, name, amount, currency, next_due_date, cadence}` |
| `bill.due` | Bill due date reached | `{id, name, amount, next_due_date}` |
| `budget.threshold_reached` | Spending exceeds budget threshold | `{category, threshold, current_amount}` |
| `import.completed` | Statement import finished | `{inserted, duplicates}` |
| `import.failed` | Statement import failed | `{error}` |
| `ping` | Test event via `/webhooks/<id>/test` | `{message}` |
| `*` | Wildcard — matches all events | Varies |

## Retry & Failure Handling

- **Retry schedule:** Exponential backoff — 1s, 5s, 30s, 2min, 10min
- **Max retries:** 5 attempts per delivery
- **Dead letter:** After 5 failed attempts, delivery is marked `dead`
- **Auto-disable:** Webhook is automatically disabled after 10 consecutive delivery failures across all events
- **Re-enable:** Use `PATCH /webhooks/<id>` with `{"active": true}` to re-enable (resets failure counter)

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhooks` | Register a new webhook |
| `GET` | `/webhooks` | List all user webhooks |
| `GET` | `/webhooks/<id>` | Get webhook details |
| `PATCH` | `/webhooks/<id>` | Update webhook (url, events, active) |
| `DELETE` | `/webhooks/<id>` | Delete webhook and all deliveries |
| `GET` | `/webhooks/<id>/deliveries` | List delivery attempts (paginated) |
| `POST` | `/webhooks/<id>/test` | Send a test ping event |

### Delivery Log Entry

```json
{
  "id": 1,
  "delivery_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "expense.created",
  "status": "success",
  "attempts": 1,
  "max_retries": 5,
  "last_status_code": 200,
  "last_response_ms": 145,
  "last_error": null,
  "next_retry_at": null,
  "created_at": "2026-02-15T12:00:00",
  "completed_at": "2026-02-15T12:00:01"
}
```
