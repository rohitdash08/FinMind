# Webhook Event System — Developer Reference

## Overview

This system emits signed HTTP POST requests to registered subscriber URLs whenever key events occur in the application. It provides **at-least-once delivery** with automatic retries and dead-letter handling.

---

## Supported Event Types

| Event Type             | Triggered When                        |
|------------------------|---------------------------------------|
| `expense.created`      | A new expense is recorded             |
| `expense.updated`      | An expense is modified                |
| `expense.deleted`      | An expense is deleted                 |
| `bill.created`         | A new bill is created                 |
| `bill.paid`            | A bill is marked as paid              |
| `settlement.completed` | A group settlement is finalised       |

---

## Payload Schema (v1.0)

Every POST body is JSON with the following shape:

```json
{
  "version": "1.0",
  "idempotency_key": "<hex-64-char>",
  "event": "expense.created",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "data": { /* event-specific fields */ }
}
```

### Headers sent with every request

| Header                    | Value / Purpose                                      |
|---------------------------|------------------------------------------------------|
| `Content-Type`            | `application/json`                                   |
| `X-Webhook-Signature`     | `sha256=<hmac-hex>` — verify with your secret        |
| `X-Webhook-Version`       | `1.0` — bump on breaking schema changes              |
| `X-Webhook-Event`         | e.g. `expense.created`                               |
| `X-Idempotency-Key`       | Same as `payload.idempotency_key`                    |

---

## Signature Verification

Compute `HMAC-SHA256` over the **raw request body string** using your subscription secret, then compare to the value after `sha256=` in `X-Webhook-Signature`.

### Node.js example

```js
const crypto = require('crypto');

function verify(rawBody, secret, signatureHeader) {
  const expected = 'sha256=' +
    crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signatureHeader)
  );
}
```

---

## Idempotency & Deduplication

**At-least-once delivery** means the same event may arrive more than once during retries.  
Consumers **MUST** deduplicate using the `idempotency_key` field:

- Store processed keys (e.g., in Redis or a DB table) with a TTL of ≥ 48 hours.
- Before processing, check if the key was already handled; skip if so.
- Return `HTTP 2xx` even for duplicate deliveries to stop further retries.

---

## Retry & Failure Policy

| Attempt | Delay before retry |
|---------|-------------------|
| 1 → 2   | 30 seconds        |
| 2 → 3   | 5 minutes         |
| 3 → 4   | 30 minutes        |
| 4 → 5   | 2 hours           |
| 5       | (final; no retry) |

- **Timeout**: each request is aborted after **10 seconds**.
- **Max payload**: requests exceeding **1 MB** are skipped.
- **404 / 410**: subscription is immediately soft-disabled; no retries.
- **Auto-disable**: after **5 consecutive event-level failures** the subscription is soft-disabled and the owner is notified.
- **Re-enable**: disabled subscriptions can be re-activated via the dashboard after the endpoint is fixed.

---

## Schema Versioning

- The current schema version is `1.0`, sent in both the payload and `X-Webhook-Version`.
- **Non-breaking additions** (new optional fields) will NOT increment the version.
- **Breaking changes** will increment to `1.1`, `2.0`, etc. with a deprecation notice and a migration window.
- Consumers should check `X-Webhook-Version` (or `payload.version`) and handle unknown versions gracefully.

---

## Quick Start

```ts
import { createSubscription, emitEvent } from '@/lib/webhook';

// Register a webhook (do this once; store the returned secret securely)
const { subscription, secret } = await createSubscription(
  userId,
  'https://your-app.com/webhooks/fimanager',
  ['expense.created', 'bill.paid']
);
console.log('Save this secret once:', secret);

// Emit an event (call this from your domain logic)
await emitEvent('expense.created', { id: 123, amount: 49.99, currency: 'USD' }, userId);
```
