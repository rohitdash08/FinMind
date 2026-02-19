# FinMind Webhook System

## Overview

The FinMind webhook system allows you to subscribe to events that occur in your FinMind account and receive real-time notifications via HTTP POST requests. This enables seamless integration with external systems and automation of workflows.

## Key Features

- **Signed Delivery**: All webhook payloads are cryptographically signed using HMAC-SHA256, allowing you to verify authenticity
- **Reliable Delivery**: Automatic retry mechanism with exponential backoff (up to 5 attempts)
- **Comprehensive Events**: Track changes across expenses, bills, categories, and reminders
- **Simple REST API**: Easy-to-use endpoints for managing webhooks

## Getting Started

### Creating a Webhook

To create a webhook, make a POST request to `/api/webhooks`:

```bash
curl -X POST https://api.finmind.com/api/webhooks \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook",
    "events": ["expense.created", "bill.paid"]
  }'
```

Response:
```json
{
  "id": 1,
  "url": "https://your-domain.com/webhook",
  "secret": "whsec_1234567890abcdef",
  "events": ["expense.created", "bill.paid"],
  "active": true,
  "created_at": "2024-02-19T10:00:00",
  "updated_at": "2024-02-19T10:00:00"
}
```

**Important**: Save the `secret` securely. You'll need it to verify webhook signatures.

### Managing Webhooks

#### List all webhooks
```bash
curl https://api.finmind.com/api/webhooks \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Get a specific webhook
```bash
curl https://api.finmind.com/api/webhooks/{webhook_id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Update a webhook
```bash
curl -X PATCH https://api.finmind.com/api/webhooks/{webhook_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook/new",
    "events": ["expense.created", "expense.updated", "bill.paid"]
  }'
```

#### Delete a webhook
```bash
curl -X DELETE https://api.finmind.com/api/webhooks/{webhook_id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Webhook Payloads

### Payload Format

All webhook payloads follow this format:

```json
{
  "type": "expense.created",
  "timestamp": "2024-02-19T10:00:00",
  "data": {
    "id": 123,
    "user_id": 456,
    "amount": 50.00,
    "currency": "USD",
    "notes": "Lunch",
    "spent_at": "2024-02-19"
  }
}
```

### Supported Events

#### Expense Events
- **`expense.created`**: Fired when a new expense is created
  - Data includes: `id`, `user_id`, `amount`, `currency`, `category_id`, `notes`, `spent_at`, `created_at`

- **`expense.updated`**: Fired when an expense is updated
  - Data includes: all expense fields

- **`expense.deleted`**: Fired when an expense is deleted
  - Data includes: `id`, `user_id`, `deleted_at`

#### Bill Events
- **`bill.created`**: Fired when a new bill is created
  - Data includes: `id`, `user_id`, `name`, `amount`, `currency`, `next_due_date`, `cadence`

- **`bill.updated`**: Fired when a bill is updated
  - Data includes: all bill fields

- **`bill.deleted`**: Fired when a bill is deleted
  - Data includes: `id`, `user_id`, `deleted_at`

- **`bill.paid`**: Fired when a bill is marked as paid
  - Data includes: `id`, `user_id`, `name`, `amount`, `paid_at`

#### Category Events
- **`category.created`**: Fired when a new category is created
  - Data includes: `id`, `user_id`, `name`, `created_at`

- **`category.updated`**: Fired when a category is updated
  - Data includes: all category fields

- **`category.deleted`**: Fired when a category is deleted
  - Data includes: `id`, `user_id`, `deleted_at`

#### Reminder Events
- **`reminder.created`**: Fired when a reminder is created
  - Data includes: `id`, `user_id`, `bill_id`, `message`, `send_at`, `channel`

- **`reminder.sent`**: Fired when a reminder is sent
  - Data includes: all reminder fields, `sent_at`

## Verifying Webhook Signatures

All webhooks include an `X-FinMind-Signature` header containing an HMAC-SHA256 signature of the request body. Verify this signature to ensure the webhook came from FinMind.

### Verification Steps

1. Get the signature from the `X-FinMind-Signature` header
2. Get the timestamp from the `X-FinMind-Timestamp` header
3. Compute the HMAC-SHA256 of the raw request body using your webhook secret
4. Compare the computed signature with the one from the header using constant-time comparison

### Python Example

```python
import hmac
import hashlib
import json
from flask import Flask, request

app = Flask(__name__)
WEBHOOK_SECRET = "whsec_1234567890abcdef"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    # Get signature and payload
    signature = request.headers.get('X-FinMind-Signature')
    payload = request.data  # Raw bytes
    
    # Compute expected signature
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Verify using constant-time comparison
    if not hmac.compare_digest(signature, expected_signature):
        return {'error': 'Invalid signature'}, 401
    
    # Process the webhook
    data = json.loads(payload)
    print(f"Received event: {data['type']}")
    
    return {'ok': True}, 200
```

### Node.js Example

```javascript
const express = require('express');
const crypto = require('crypto');
const app = express();

const WEBHOOK_SECRET = 'whsec_1234567890abcdef';

app.post('/webhook', express.raw({type: 'application/json'}), (req, res) => {
  const signature = req.headers['x-finmind-signature'];
  const payload = req.body;
  
  // Compute expected signature
  const expectedSignature = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(payload)
    .digest('hex');
  
  // Verify signature
  if (signature !== expectedSignature) {
    return res.status(401).json({error: 'Invalid signature'});
  }
  
  // Process the webhook
  const data = JSON.parse(payload);
  console.log(`Received event: ${data.type}`);
  
  res.json({ok: true});
});
```

## Retry Mechanism

FinMind automatically retries failed webhook deliveries with exponential backoff:

- **Attempt 1**: Immediate
- **Attempt 2**: 60 seconds later
- **Attempt 3**: 120 seconds later
- **Attempt 4**: 240 seconds later
- **Attempt 5**: 480 seconds later

After 5 failed attempts, the webhook is marked as failed and no further retries are attempted.

## Webhook Event History

You can view the delivery history for a webhook:

```bash
curl https://api.finmind.com/api/webhooks/{webhook_id}/events \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "events": [
    {
      "id": 1,
      "event_type": "expense.created",
      "status": "delivered",
      "delivery_attempts": 1,
      "last_error": null,
      "created_at": "2024-02-19T10:00:00",
      "last_attempted_at": "2024-02-19T10:00:05",
      "delivered_at": "2024-02-19T10:00:05"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 1,
    "pages": 1
  }
}
```

## Best Practices

1. **Verify Signatures**: Always verify webhook signatures before processing
2. **Idempotency**: Design webhook handlers to be idempotent (safe to call multiple times)
3. **Timeouts**: Return a 2xx status code quickly; process webhook data asynchronously if needed
4. **Logging**: Log all webhook requests for debugging
5. **Error Handling**: Return error responses to trigger retries
6. **Health Checks**: Monitor webhook delivery status regularly

## API Reference

### POST /api/webhooks
Create a new webhook.

**Request:**
```json
{
  "url": "https://your-domain.com/webhook",
  "events": ["expense.created", "bill.paid"]
}
```

**Response:** `201 Created`

---

### GET /api/webhooks
List all webhooks for the current user.

**Response:** `200 OK` - Array of webhooks

---

### GET /api/webhooks/{webhook_id}
Get a specific webhook.

**Response:** `200 OK`

---

### PATCH /api/webhooks/{webhook_id}
Update a webhook.

**Request:**
```json
{
  "url": "https://your-domain.com/webhook/new",
  "events": ["expense.created"]
}
```

**Response:** `200 OK`

---

### DELETE /api/webhooks/{webhook_id}
Delete a webhook.

**Response:** `200 OK`

---

### GET /api/webhooks/{webhook_id}/events
Get event delivery history for a webhook.

**Query Parameters:**
- `page`: Page number (default: 1)
- `limit`: Results per page (default: 50, max: 100)

**Response:** `200 OK`

---

### GET /api/webhooks/docs/events
Get documentation for all supported webhook events.

**Response:** `200 OK`

## Processing Webhooks

### CLI Command

You can manually trigger webhook delivery processing:

```bash
flask deliver-webhooks --batch-size=100 --delay-minutes=0
```

This is useful for:
- Processing queued webhooks
- Retrying failed deliveries
- Running as a cron job for background processing

### Automatic Processing

For production, configure this command to run periodically (e.g., every minute via cron):

```bash
*/1 * * * * cd /path/to/finmind && flask deliver-webhooks
```

Or integrate with task queue systems like Celery for better control.

## Troubleshooting

### Webhook Not Received

1. Verify the webhook URL is correct and publicly accessible
2. Check firewall/security group rules
3. Review webhook event history for delivery status
4. Look for error messages in the `last_error` field

### Signature Verification Failed

1. Ensure you're using the correct webhook secret
2. Verify you're using the raw request body (not parsed JSON)
3. Use constant-time comparison to prevent timing attacks

### High Failure Rate

1. Check your webhook handler for errors
2. Ensure your endpoint returns a 2xx status code
3. Monitor server logs and network connectivity
4. Review FinMind logs for delivery errors

## Support

For issues or questions about webhooks, please:
1. Check this documentation
2. Review webhook event history
3. Enable debug logging
4. Contact support with webhook ID and event details
