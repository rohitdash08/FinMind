# Webhook Event System

## Overview
Signed webhook delivery system for FinMind events.

## Features
- ✅ Signed delivery (HMAC-SHA256)
- ✅ Retry with exponential backoff
- ✅ Event type filtering
- ✅ Idempotent event IDs

## Event Types

| Event | Description |
|-------|-------------|
| `expense.created` | New expense added |
| `expense.updated` | Expense modified |
| `expense.deleted` | Expense removed |
| `budget.alert` | Budget threshold crossed |
| `reminder.triggered` | Reminder fired |

## Usage

```typescript
import { webhookManager, WebhookEventTypes } from './lib/webhook';

// Register webhook
webhookManager.registerWebhook('my-integration', {
  url: 'https://api.example.com/webhooks/finmind',
  secret: 'whsec_...',
  events: ['expense.created', 'expense.updated'],
  retryAttempts: 3
});

// Emit events
await webhookManager.emitExpenseCreated(newExpense);
```

## Webhook Payload

```json
{
  "id": "evt_1234567890_abc123",
  "type": "expense.created",
  "payload": { /* expense data */ },
  "timestamp": "2026-03-06T10:55:00.000Z",
  "signature": "sha256=..."
}
```

## Verification

```typescript
const isValid = verifySignature(payload, signature, secret);
```
