# FinMind Webhooks 🐾⚡️

FinMind provides a robust webhook system to enable real-time integrations. You can receive notifications for key events like expense creation, category updates, and bill reminders.

## Security (HMAC-SHA256)

All webhook payloads are signed using **HMAC-SHA256**. The signature is sent in the `X-FinMind-Signature` header.

### Signature Verification (Python Example)

```python
import hmac
import hashlib
import json

def verify_signature(payload_body, secret, signature_header):
    # payload_body should be the raw bytes from the request
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_signature}", signature_header)
```

## Event Types

| Event Name | Description |
| :--- | :--- |
| `expense.created` | Emitted when a new expense record is successfully created. |
| `expense.updated` | Emitted when an existing expense record is modified. |
| `expense.deleted` | Emitted when an expense record is deleted. |
| `category.created` | Emitted when a new category is added to the system. |
| `bill.reminder` | Emitted when a bill reminder is triggered by the system. |

## Delivery & Retries

FinMind uses an **Exponential Backoff** strategy for failed webhook deliveries:
- **Max Retries**: 5
- **Strategy**: Wait time increases exponentially (2^attempt seconds).
- **Timeouts**: The system waits up to 10 seconds for a response.

## Payload Format

Example `expense.created` payload:

```json
{
  "event": "expense.created",
  "timestamp": 1708142400,
  "data": {
    "id": 123,
    "amount": 50.00,
    "currency": "USD",
    "notes": "Lunch with team",
    "spent_at": "2026-02-17"
  }
}
```

---
*FinMind - Manage your finances with peace of mind.*
