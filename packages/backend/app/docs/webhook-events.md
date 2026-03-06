# Webhook Event Types

FinMind emits signed webhook events to registered endpoints when key actions occur.

## Security: Verifying Signatures

Every request includes an X-FinMind-Signature-256 header.
Verify it before processing:

```python
import hashlib, hmac

def verify(secret: str, payload: bytes, signature: str) -> bool:
    expected = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Event Catalog

| Event | Trigger |
|---|---|
| expense.created | New expense added |
| expense.updated | Expense modified |
| expense.deleted | Expense removed |
| bill.created | New bill registered |
| bill.paid | Bill marked as paid |
| bill.updated | Bill details updated |
| reminder.sent | Reminder dispatched to user |

## Retry Policy

Failed deliveries are retried up to 3 times with delays of 10s, 30s, and 60s.

## Endpoints

- POST /webhooks - Register endpoint
- GET /webhooks - List your endpoints
- DELETE /webhooks/:id - Deactivate endpoint
- GET /webhooks/deliveries - View delivery history
