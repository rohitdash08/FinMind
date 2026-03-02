# FinMind Webhook System

## Overview

The FinMind webhook system enables real-time event notifications to external services.

## Features

- **Signed Deliveries**: All webhooks are signed with HMAC-SHA256 for verification
- **Retry Logic**: Automatic retry with exponential backoff (5 attempts)
- **Event Filtering**: Subscribe to specific event types
- **Delivery Logs**: Track all delivery attempts and responses
- **Failure Handling**: Auto-deactivate subscriptions after repeated failures

## Supported Events

| Event Type | Description |
|------------|-------------|
| `expense.created` | New expense added |
| `expense.updated` | Expense modified |
| `expense.deleted` | Expense removed |
| `bill.created` | New bill created |
| `bill.updated` | Bill modified |
| `bill.due` | Bill due date reached |
| `recurring_expense.created` | Recurring expense setup |
| `recurring_expense.triggered` | Recurring expense processed |
| `user_subscription.created` | New subscription started |
| `user_subscription.cancelled` | Subscription cancelled |

## API Endpoints

### Create Webhook
```http
POST /api/webhooks
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "url": "https://your-app.com/webhook",
  "events": ["expense.created", "bill.due"],
  "description": "My integration"
}
```

**Response:**
```json
{
  "id": 1,
  "url": "https://your-app.com/webhook",
  "events": ["expense.created", "bill.due"],
  "status": "active",
  "secret": "abc123...",  // Save this!
  "created_at": "2024-01-01T00:00:00Z"
}
```

### List Webhooks
```http
GET /api/webhooks
Authorization: Bearer <jwt_token>
```

### Update Webhook
```http
PUT /api/webhooks/{id}
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "url": "https://new-url.com/webhook",
  "events": ["expense.created"]
}
```

### Delete Webhook
```http
DELETE /api/webhooks/{id}
Authorization: Bearer <jwt_token>
```

### Regenerate Secret
```http
POST /api/webhooks/{id}/regenerate-secret
Authorization: Bearer <jwt_token>
```

### List Delivery History
```http
GET /api/webhooks/{id}/deliveries
Authorization: Bearer <jwt_token>
```

### List Event Types
```http
GET /api/webhooks/events
```

## Webhook Payload

```json
{
  "id": 123,
  "event": "expense.created",
  "created_at": "2024-01-01T12:00:00Z",
  "data": {
    "id": 456,
    "amount": 100.00,
    "currency": "INR",
    "notes": "Lunch",
    "spent_at": "2024-01-01"
  }
}
```

## Signature Verification

Webhooks include a signature header for security:

```
X-FinMind-Signature: sha256=<hex_signature>
```

### Python Example
```python
import hmac
import hashlib

payload = request.body
signature = request.headers['X-FinMind-Signature']
secret = 'your-webhook-secret'

expected = hmac.new(
    secret.encode(),
    payload.encode(),
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(f"sha256={expected}", signature):
    raise ValueError("Invalid signature")
```

### Node.js Example
```javascript
const crypto = require('crypto');

const signature = req.headers['x-finmind-signature'];
const secret = 'your-webhook-secret';

const expected = crypto
  .createHmac('sha256', secret)
  .update(req.body)
  .digest('hex');

if (`sha256=${expected}` !== signature) {
  throw new Error('Invalid signature');
}
```

## Retry Schedule

If delivery fails, retries occur at:
- 1 minute
- 5 minutes
- 15 minutes
- 1 hour
- 2 hours

After 10 consecutive failures, the subscription is automatically deactivated.

## Response Requirements

Your endpoint should return:
- **200-299**: Success
- **Other**: Will be retried

Respond quickly (< 30s) to avoid timeouts.

## Testing

Send a test event:
```http
POST /api/webhooks/test
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "url": "https://your-app.com/webhook"
}
```

## Database Migration

Run the migration to add webhook tables:
```bash
psql -d finmind -f packages/backend/app/db/migrations/add_webhooks.sql
```
