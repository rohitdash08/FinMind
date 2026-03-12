# Resilient Background Job Queue

Implemented for [Issue #130](../../issues/130).

## Overview

`JobQueue` wraps any async function with **exponential backoff retry** and **lifecycle monitoring**. It is designed for API calls that can experience transient failures (network blips, 5xx responses) while safely ignoring permanent errors (4xx).

## Quick Start

```ts
import { JobQueue, JobMonitor } from '@/lib/jobQueue';
import { getDashboardSummary } from '@/api/dashboard';

// 1. Create a shared monitor with lifecycle hooks
const monitor = new JobMonitor({
  onSuccess: (job) => console.info('Job completed', job.id),
  onRetry:   (job, attempt, err) => console.warn(`Retry #${attempt}`, err.message),
  onDead:    (job) => console.error('Job dead-lettered', job.id, job.error),
});

// 2. Create a queue (shared or per-feature)
const queue = new JobQueue({ monitor });

// 3. Enqueue a task — retries happen automatically
const summary = await queue.enqueue(() =>
  getDashboardSummary({ month: '2026-02' })
);
```

## Retry Policy

| Option | Default | Description |
|---|---|---|
| `maxAttempts` | `3` | Total attempts including the first |
| `baseDelayMs` | `200` | Base delay; doubles each retry (200 → 400 → 800 ms) |
| `isRetryable` | skip 4xx | Return `false` to abort retries immediately |

Customise the policy at queue creation:

```ts
const queue = new JobQueue({
  policy: {
    maxAttempts: 5,
    baseDelayMs: 500,
    isRetryable: (err) => !err.message.includes('401'),
  },
});
```

## Job Lifecycle

```
PENDING → RUNNING → COMPLETED          (happy path)
                  → RUNNING (retry) → … → COMPLETED
                  → FAILED                (permanent 4xx error)
                  → DEAD                 (all retries exhausted)
```

## Dead-Letter Queue

Jobs that exhaust all retries are moved to `DEAD` state and can be inspected:

```ts
const dead = monitor.getDeadJobs();
dead.forEach((job) => {
  console.error(`Job ${job.id} failed after ${job.attempts} attempts:`, job.error);
});
```

Call `monitor.clear()` periodically to prevent unbounded memory growth in long-running processes.

## Memory Management

- The monitor stores **all** job records in memory. For high-throughput scenarios, flush completed jobs regularly with `monitor.clear()` or implement a retention policy using `monitor.getJob(id)` and custom eviction logic.
- Each `JobQueue` instance creates an isolated promise chain per job. There are no global listeners and no cross-job side effects.

## Testing

Use `jest.useFakeTimers()` to fast-forward backoff delays:

```ts
jest.useFakeTimers();

const promise = queue.enqueue(task);
jest.runAllTimers(); // advance all pending setTimeout calls
const result = await promise;
```

See `app/src/__tests__/jobQueue.test.ts` for full examples.
