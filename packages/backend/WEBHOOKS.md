# Webhook Event System

## Overview

FinMind's webhook system allows you to receive real-time notifications when key events occur in your application. Webhooks are delivered via HTTPS POST requests with HMAC-SHA256 signatures for security.

## Features

- **Signed Delivery**: All webhook payloads are signed using HMAC-SHA256
- **Automatic Retry**: Failed deliveries are retried with exponential backoff (5 attempts)
- **Event Filtering**: Subscribe to specific events or use wildcards
- **Delivery Tracking**: Monitor delivery status and retry history

## Supported Event Types

| Event Type | Description |
|------------|-------------|
| `expense.created` | New expense created |
| `expense.updated` | Expense updated |
| `expense.deleted` | Expense deleted |
| `bill.created` | New bill created |
| `bill.updated` | Bill updated |
| `bill.deleted` | Bill deleted |
| `bill.paid` | Bill marked as paid |
| `reminder.sent` | Reminder notification sent |
| `category.created` | New category created |
| `category.updated` | Category updated |
| `category.deleted` | Category deleted |

## API Endpoints

### Create Webhook Endpoint

```http
POST /webhooks
Authorization: Bearer <token>
Content-Type: application/json

{
  "url": "https://your-domain.com/webhook",
  "events": ["expense.created", "bill.paid"],
  "active": true
}
```

**Response:**
```json
{
  "id": 1,
  "url": "https://your-domain.com/webhook",
  "secret": "generated-secret-key",
  "events": ["expense.created", "bill.paid"],
  "active": true,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00"
}
```

**Important**: Save the `secret` - you'll need it to verify webhook signatures.

### List Webhook Endpoints

```http
GET /webhooks
Authorization: Bearer <token>
```

### Get Webhook Endpoint

```http
GET /webhooks/<webhook_id>
Authorization: Bearer <token>
```

### Update Webhook Endpoint

```http
PATCH /webhooks/<webhook_id>
Authorization: Bearer <token>
Content-Type: application/json

{
  "url": "https://new-domain.com/webhook",
  "events": ["*"],
  "active": false
}
```

### Delete Webhook Endpoint

```http
DELETE /webhooks/<webhook_id>
Authorization: Bearer <token>
```

### Regenerate Secret

```http
POST /webhooks/<webhook_id>/regenerate-secret
Authorization: Bearer <token>
```

### List Webhook Events

```http
GET /webhooks/events?page=1&page_size=50&type=expense.created
Authorization: Bearer <token>
```

### Get Delivery Statistics

```http
GET /webhooks/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_events": 100,
  "total_deliveries": 200,
  "successful_deliveries": 195,
  "failed_deliveries": 5,
  "pending_deliveries": 0,
  "success_rate": 97.5
}
```

### Retry Failed Webhooks

```http
POST /webhooks/retry
Authorization: Bearer <token>
```

## Webhook Payload Format

All webhook deliveries use the following format:

```json
{
  "id": 123,
  "type": "expense.created",
  "created_at": "2024-01-01T12:00:00",
  "data": {
    "id": 456,
    "amount": 100.00,
    "currency": "USD",
    "notes": "Lunch"
  }
}
```

## Signature Verification

Every webhook request includes these headers:

- `X-FinMind-Signature`: HMAC-SHA256 signature of the payload
- `X-FinMind-Event`: Event type (e.g., "expense.created")
- `X-FinMind-Delivery`: Unique delivery ID

### Verifying Signatures (Python)

```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

# Example usage in Flask
from flask import request

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get('X-FinMind-Signature')
    event_type = request.headers.get('X-FinMind-Event')
    
    if not verify_webhook_signature(payload, signature, YOUR_SECRET):
        return 'Invalid signature', 401
    
    data = request.get_json()
    # Process webhook...
    
    return 'OK', 200
```

### Verifying Signatures (Node.js)

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSignature)
  );
}

// Example usage in Express
app.post('/webhook', express.text({type: '*/*'}), (req, res) => {
  const payload = req.body;
  const signature = req.headers['x-finmind-signature'];
  const eventType = req.headers['x-finmind-event'];
  
  if (!verifyWebhookSignature(payload, signature, YOUR_SECRET)) {
    return res.status(401).send('Invalid signature');
  }
  
  const data = JSON.parse(payload);
  // Process webhook...
  
  res.status(200).send('OK');
});
```

## Retry Logic

Failed webhook deliveries are automatically retried with exponential backoff:

1. **Attempt 1**: Immediate
2. **Attempt 2**: After 1 minute
3. **Attempt 3**: After 5 minutes
4. **Attempt 4**: After 15 minutes
5. **Attempt 5**: After 1 hour
6. **Attempt 6**: After 2 hours

After 5 failed attempts, the delivery is marked as permanently failed.

## Best Practices

1. **Return 2xx Quickly**: Your webhook endpoint should return a 200-299 status code within 10 seconds
2. **Process Asynchronously**: Queue webhook processing to avoid timeouts
3. **Verify Signatures**: Always verify the HMAC signature before processing
4. **Handle Duplicates**: Use the webhook event ID to detect and skip duplicate deliveries
5. **Monitor Failures**: Check `/webhooks/stats` regularly to identify delivery issues
6. **Use HTTPS**: Webhook URLs must use HTTPS for security

## Wildcard Subscriptions

Subscribe to all events using the wildcard `*`:

```json
{
  "url": "https://your-domain.com/webhook",
  "events": ["*"]
}
```

## Testing Webhooks

You can use tools like:
- [webhook.site](https://webhook.site) - Inspect webhook payloads
- [ngrok](https://ngrok.com) - Expose local development server
- [RequestBin](https://requestbin.com) - Capture and inspect webhooks

## Error Handling

Common error responses:

| Status Code | Description |
|-------------|-------------|
| 400 | Invalid request (missing URL, invalid events) |
| 401 | Unauthorized (invalid token) |
| 404 | Webhook endpoint not found |
| 409 | Conflict (duplicate webhook) |

## Rate Limits

- Maximum 10 webhook endpoints per user
- Maximum 100 events returned per page
- Webhook delivery timeout: 10 seconds

## Support

For issues or questions about webhooks:
- Check delivery status: `GET /webhooks/stats`
- View event history: `GET /webhooks/events`
- Retry failed deliveries: `POST /webhooks/retry`
