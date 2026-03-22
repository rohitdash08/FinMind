# FinMind Webhooks

FinMind can notify your application in real time whenever key financial events occur.
Signed HTTP POST requests are delivered to your registered endpoint with exponential-backoff retry.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Event Types](#event-types)
3. [Payload Structure](#payload-structure)
4. [Signature Verification](#signature-verification)
5. [Retry Policy](#retry-policy)
6. [API Reference](#api-reference)
7. [Delivery Logs](#delivery-logs)

---

## Quick Start

```bash
# 1. Register an endpoint
curl -X POST https://api.finmind.app/webhooks/ \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.example.com/hooks/finmind",
    "secret": "your-secret-at-least-16-chars",
    "events": ["expense.created", "bill.paid"]
  }'
# → {"id": 1, "url": "...", "events": [...], "active": true}
```

---

## Event Types

| Event | Fired when |
|---|---|
| `expense.created` | A new expense is recorded |
| `expense.updated` | An existing expense is edited |
| `expense.deleted` | An expense is removed |
| `bill.created` | A new bill is added |
| `bill.paid` | A bill is marked as paid |
| `budget.exceeded` | Monthly spending crosses a budget threshold |
| `reminder.fired` | A scheduled reminder is triggered |

---

## Payload Structure

Every request body is a JSON object with two top-level keys:

```json
{
  "event": "expense.created",
  "data": { ... }
}
```

### `expense.created` / `expense.updated`

```json
{
  "event": "expense.created",
  "data": {
    "id": 42,
    "amount": "1500.00",
    "currency": "INR",
    "expense_type": "EXPENSE",
    "category_id": 3,
    "notes": "Grocery run",
    "spent_at": "2026-03-22",
    "created_at": "2026-03-22T10:30:00"
  }
}
```

### `bill.paid`

```json
{
  "event": "bill.paid",
  "data": {
    "id": 7,
    "name": "Electricity",
    "amount": "800.00",
    "due_date": "2026-03-25",
    "paid_at": "2026-03-22T14:05:00"
  }
}
```

### `budget.exceeded`

```json
{
  "event": "budget.exceeded",
  "data": {
    "month": "2026-03",
    "budget": "10000.00",
    "spent": "10450.75",
    "currency": "INR"
  }
}
```

---

## Signature Verification

Every delivery includes an `X-Hub-Signature-256` header:

```
X-Hub-Signature-256: sha256=<hex-digest>
```

The digest is computed as `HMAC-SHA256(secret, raw_request_body)`.

### Verification examples

**Python**
```python
import hashlib, hmac

def verify_signature(secret: str, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)

# Flask / FastAPI usage
from flask import request, abort

@app.post("/hooks/finmind")
def receive():
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature("your-secret", request.data, sig):
        abort(401)
    payload = request.get_json()
    ...
```

**Node.js**
```js
const crypto = require("crypto");

function verifySignature(secret, rawBody, header) {
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(rawBody)
    .digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(header)
  );
}
```

> **Always** use a constant-time comparison (`hmac.compare_digest` / `timingSafeEqual`)
> to prevent timing attacks.

---

## Retry Policy

If your endpoint returns a non-2xx status code or fails to respond within **10 seconds**, FinMind retries with exponential backoff:

| Attempt | Delay before retry |
|---|---|
| 1 (initial) | — |
| 2 | 2 s |
| 3 | 4 s |
| 4 | 8 s |
| 5 | 16 s |

After 5 failed attempts the delivery is marked **failed** and recorded in the delivery log.
You can inspect failures and replay manually via the [Delivery Logs](#delivery-logs) API.

---

## API Reference

All endpoints require `Authorization: Bearer <JWT>`.

### Register endpoint

```
POST /webhooks/
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `url` | string | ✅ | Must start with `http://` or `https://` |
| `secret` | string | ✅ | Min 16 characters |
| `events` | string[] | ✅ | See [Event Types](#event-types) |

### List endpoints

```
GET /webhooks/
```

### Update endpoint

```
PATCH /webhooks/{id}
```

Accepts `active` (bool) and/or `events` (string[]).

### Delete endpoint

```
DELETE /webhooks/{id}
```

---

## Delivery Logs

```
GET /webhooks/{id}/deliveries
```

Returns the last 50 delivery attempts (newest first):

```json
[
  {
    "id": 101,
    "event": "expense.created",
    "status_code": 200,
    "attempts": 1,
    "success": true,
    "error": null,
    "delivered_at": "2026-03-22T10:30:01.123Z",
    "created_at": "2026-03-22T10:30:00.000Z"
  }
]
```

Use these logs to diagnose delivery failures without needing external tooling.
