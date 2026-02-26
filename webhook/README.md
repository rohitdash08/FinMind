# FinMind Webhook Event System

Signed webhook delivery with HMAC-SHA256, async dispatch, and exponential-backoff retries.

## Features

- **Signed delivery** – every payload is signed with HMAC-SHA256 using a per-endpoint shared secret
- **Retry with backoff** – failed deliveries retry up to 5 times with exponential backoff (1s, 2s, 4s, 8s, 16s)
- **Delivery tracking** – each delivery is tracked as `pending` → `delivered` | `failed`
- **Event filtering** – endpoints subscribe to specific event types (or wildcard for all)
- **Async-first** – built on `asyncio` + `aiohttp` for high-throughput delivery
- **FastAPI integration** – optional router for endpoint management via REST API

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
import asyncio
from webhook.middleware import WebhookManager

manager = WebhookManager()

# Register an endpoint
manager.register_endpoint(
    url="https://your-app.com/webhooks",
    secret="whsec_your_secret_key",
    events={"transaction.created", "anomaly.detected"},
)

# Emit an event
asyncio.run(manager.emit("transaction.created", {
    "transaction_id": "txn_abc123",
    "amount": 150.00,
    "currency": "USD",
}))
```

## Event Catalog

| Event Type | Description |
|---|---|
| `transaction.created` | A new transaction was recorded |
| `transaction.updated` | An existing transaction was modified |
| `transaction.deleted` | A transaction was removed |
| `account.connected` | A financial account was linked |
| `account.disconnected` | A financial account was unlinked |
| `account.synced` | Account data was refreshed |
| `budget.exceeded` | Spending exceeded the budget threshold |
| `budget.warning` | Spending is approaching the budget limit |
| `anomaly.detected` | Unusual activity or potential fraud detected |
| `export.completed` | A data export finished processing |

## Signature Verification

Every webhook POST includes these headers:

| Header | Description |
|---|---|
| `X-Webhook-Signature` | `sha256=<hex-digest>` HMAC-SHA256 of the payload |
| `X-Webhook-Timestamp` | ISO-8601 timestamp (used in signing body) |
| `X-Webhook-Event` | Event type string |
| `X-Webhook-Event-Id` | Unique event identifier |

### Verifying in your handler

```python
from webhook.signer import WebhookSigner

signer = WebhookSigner(secret="whsec_your_secret_key")

# In your HTTP handler:
signature = request.headers["X-Webhook-Signature"]
timestamp = request.headers["X-Webhook-Timestamp"]
payload = request.json()

if not signer.verify(payload, signature, timestamp=timestamp):
    return Response(status_code=401)
```

## Retry Behaviour

| Attempt | Delay |
|---|---|
| 1 | immediate |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds |
| 5 | 8 seconds |
| 6 | 16 seconds |

After all retries are exhausted the delivery is marked `failed`. A 2xx response at any point marks it `delivered`.

## FastAPI Integration

```python
from fastapi import FastAPI
from webhook.middleware import WebhookManager, create_fastapi_webhook_router

app = FastAPI()
manager = WebhookManager()
app.include_router(create_fastapi_webhook_router(manager))

# Emit events from anywhere in your app:
@app.post("/transactions")
async def create_transaction():
    # ... create transaction ...
    await manager.emit("transaction.created", {"id": "txn_1", "amount": 42.0})
```

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks` | Register a new endpoint |
| `GET` | `/webhooks` | List all endpoints |
| `DELETE` | `/webhooks/{id}` | Remove an endpoint |

## Component Overview

| Module | Purpose |
|---|---|
| `webhook/events.py` | Event type enum and groupings |
| `webhook/models.py` | Pydantic data models |
| `webhook/signer.py` | HMAC-SHA256 signing/verification |
| `webhook/dispatcher.py` | Async delivery with retry |
| `webhook/registry.py` | Endpoint CRUD |
| `webhook/middleware.py` | WebhookManager façade + FastAPI router |

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## License

MIT
