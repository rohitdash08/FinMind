# Webhook Event System

FinMind can notify external systems whenever key events happen in a user's
account (e.g. expense created, bill paid). Each delivery is signed with the
subscriber's secret so receivers can verify authenticity.

## Managing webhooks

All endpoints below require a JWT access token (`Authorization: Bearer ...`).

| Method | Path                                    | Description                                          |
| ------ | --------------------------------------- | ---------------------------------------------------- |
| GET    | `/webhooks`                             | List the caller's webhooks.                          |
| POST   | `/webhooks`                             | Register a webhook. Returns the secret once.         |
| PATCH  | `/webhooks/{id}`                        | Update url / events / active flag.                   |
| DELETE | `/webhooks/{id}`                        | Remove a webhook (cascades its delivery history).    |
| GET    | `/webhooks/events`                      | Public list of supported event types.                |
| GET    | `/webhooks/{id}/deliveries`             | Last 100 delivery attempts for a webhook.            |
| POST   | `/webhooks/run`                         | Process pending retries whose backoff has elapsed.   |

### Create example

```http
POST /webhooks
Content-Type: application/json
Authorization: Bearer <token>

{
  "url": "https://example.com/finmind-hook",
  "events": ["expense.created", "bill.paid"]
}
```

Response (`201`):

```json
{
  "id": 12,
  "url": "https://example.com/finmind-hook",
  "events": ["expense.created", "bill.paid"],
  "active": true,
  "secret": "8d1c... (store this; it is not returned again)",
  "created_at": "2025-01-01T00:00:00"
}
```

`events` accepts either a list or a comma-separated string. Use `"*"` (the
default) to receive every event, or a `namespace.*` shorthand such as
`"expense.*"`.

## Event types

| Event              | When                                              |
| ------------------ | ------------------------------------------------- |
| `expense.created`  | A new expense is created (manual or import).      |
| `expense.updated`  | An expense is modified.                           |
| `expense.deleted`  | An expense is deleted.                            |
| `bill.created`     | A new bill is created.                            |
| `bill.paid`        | A bill is marked paid (next due date advanced).   |
| `reminder.created` | A reminder is created.                            |

## Delivery format

Each delivery is an HTTP `POST` with a JSON body:

```json
{
  "id": "f7b6...-uuid",
  "type": "expense.created",
  "created_at": "2025-01-01T12:00:00Z",
  "data": { "id": 99, "amount": 12.50, "currency": "USD", "...": "..." }
}
```

Headers:

- `Content-Type: application/json`
- `X-FinMind-Event` — event type (e.g. `expense.created`)
- `X-FinMind-Delivery` — unique delivery id
- `X-FinMind-Timestamp` — Unix seconds when the request was sent
- `X-FinMind-Signature` — `sha256=<hex>` HMAC-SHA256 of the raw body keyed
  with the webhook secret

### Verifying signatures (Python)

```python
import hmac, hashlib

def verify(secret: str, body: bytes, header: str) -> bool:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", header or "")
```

Receivers should respond with a `2xx` status within 5 seconds. Any other
response (or a network error) is treated as a failure and retried.

## Retry & failure handling

- Each delivery is attempted up to **5 times**.
- Backoff schedule between attempts: **30s, 1m, 5m, 15m, 30m**.
- Retries fire when an authenticated client (or a scheduled job) calls
  `POST /webhooks/run`; that endpoint picks up any delivery whose
  `next_attempt_at` has elapsed.
- After the final failed attempt the delivery is marked `FAILED` and is
  visible via `GET /webhooks/{id}/deliveries` along with the last status
  code and error.
- Deliveries always carry the same `id`, so receivers can dedupe retries
  idempotently.
