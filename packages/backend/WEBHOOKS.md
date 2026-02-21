# FinMind Webhooks Documentation

FinMind supports outgoing webhooks to notify external systems of key events.

## Signature Verification

Each webhook request includes a `X-FinMind-Signature` header. This is a HMAC SHA-256 hex digest of the JSON payload, signed with your subscription secret.

Example (Node.js):
```javascript
const crypto = require('crypto');
const signature = crypto
  .createHmac('sha256', secret)
  .update(JSON.stringify(payload))
  .digest('hex');
```

## Retry Logic

If a delivery attempt fails (status code outside 200-299), FinMind will retry up to 3 times with exponential backoff (2^n seconds).

## Event Types

### `expense.created`
Triggered when a new expense is added.
Payload: Same as Expense object.

### `expense.updated`
Triggered when an existing expense is modified.
Payload: Same as Expense object.

### `expense.deleted`
Triggered when an expense is deleted.
Payload: Same as Expense object (before deletion).

## Registration

Use the `POST /webhooks/subscribe` endpoint with your target URL. It will return a unique `secret`.
