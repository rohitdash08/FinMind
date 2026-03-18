# Resilient Background Job Retry & Monitoring

## Overview

FinMind now includes a resilient API client with automatic retry logic, exponential backoff with jitter, and a real-time request monitor that surfaces retry/failure status in the UI.

## Architecture

```
api/client.ts          → wraps every API call with retry + monitor integration
lib/retry.ts           → core retry engine (backoff, jitter, shouldRetry)
lib/request-monitor.ts → singleton tracker for all in-flight requests
hooks/use-request-monitor.ts → React hooks for consuming monitor state
components/layout/Navbar.tsx  → live network status badges
```

## Retry Configuration

Every `api()` call accepts an optional `retry` config:

```ts
// Default: 3 attempts, 500ms base, 10s cap, 0.5 jitter
api('/dashboard/summary');

// Custom overrides
api('/expenses', {
  retry: { maxAttempts: 5, baseDelayMs: 1_000, jitterFactor: 0.3 },
});

// Disable retry entirely
api('/auth/login', { retry: false });
```

### Retryable Errors

By default, requests are retried when:
- **Network failure** (`TypeError` from `fetch()`)
- **HTTP 408** Request Timeout
- **HTTP 429** Too Many Requests
- **HTTP 500/502/503/504** Server errors

Custom predicates can override `shouldRetry` in the config.

## Request Monitor

All API calls are automatically tracked. The monitor exposes:

| Field       | Description                            |
|-------------|----------------------------------------|
| `id`        | Unique request identifier              |
| `path`      | API path                               |
| `method`    | HTTP method                            |
| `attempt`   | Current retry attempt (0 = first)      |
| `status`    | `pending` → `retrying` → `succeeded` / `failed` |
| `lastError` | Error message from most recent failure |
| `startedAt` | Timestamp of initial request           |

### React Hook

```tsx
import { useRequestMonitor } from '@/hooks/use-request-monitor';

function StatusBar() {
  const { inFlight, failed, requests, clear } = useRequestMonitor();

  return (
    <div>
      {inFlight > 0 && <span>⏳ {inFlight} request(s) in flight</span>}
      {failed > 0 && <span>❌ {failed} failed</span>}
      {failed > 0 && <button onClick={clear}>Dismiss</button>}
    </div>
  );
}
```

## UI Integration

The Navbar automatically shows:
- 🔄 **Retrying badge** with spinner when requests are retrying
- ❌ **Failed badge** when requests have permanently failed

## Testing

Run with:
```bash
cd app && npm test -- --testPathPattern="(retry|request-monitor)"
```

Tests cover:
- Exponential backoff computation
- Jitter bounds
- Retry predicates (status codes, network errors)
- Full retry lifecycle (success, exhausted attempts, non-retryable)
- Monitor state transitions
- Subscriber notifications
