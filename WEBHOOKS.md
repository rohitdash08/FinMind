# FinMind Webhook System

This module provides a secure, reliable webhook event system.

## Usage
1. Initialize with a secret.
2. Emit events using `webhookManager.emit(url, event, data)`.

## Verification
Verify webhooks using the `X-FinMind-Signature` header (HMAC-SHA256).
