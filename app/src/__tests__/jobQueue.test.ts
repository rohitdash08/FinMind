/**
 * jobQueue.test.ts
 *
 * Tests for the JobQueue and JobMonitor resilience layer (Issue #130).
 *
 * WHY these test cases:
 * 1. Retry with exponential backoff — core acceptance criterion.
 * 2. No retry on permanent (4xx) errors — prevents wasted attempts and
 *    avoids hammering auth/validation endpoints that will never recover.
 * 3. Dead-letter queue after exhausted retries — ensures failed jobs are
 *    observable for manual intervention without losing error context.
 */

import { JobMonitor, JobQueue, defaultRetryPolicy } from '../lib/jobQueue';

// WHY: We fast-forward fake timers so tests don't actually wait for
// exponential backoff delays (200ms, 400ms …) during CI runs.
jest.useFakeTimers();

/** Helper: run the queue's internal promise while advancing timers. */
async function drainWithTimers(promise: Promise<unknown>): Promise<unknown> {
  // We interleave timer advancement with microtask flushing so that
  // each await sleep() inside the retry loop is resolved.
  const flushPromise = () => Promise.resolve();
  let result: unknown;
  let error: unknown;
  let settled = false;

  promise
    .then((v) => { result = v; settled = true; })
    .catch((e) => { error = e; settled = true; });

  // Advance time in small increments, flushing microtasks between each step.
  // 4 iterations covers up to 3 retries with baseDelayMs=1 in tests.
  for (let i = 0; i < 8; i++) {
    await flushPromise();
    jest.advanceTimersByTime(10_000); // jump past any backoff delay
    await flushPromise();
    if (settled) break;
  }

  if (error !== undefined) throw error;
  return result;
}

describe('JobQueue — retry & monitoring', () => {
  afterEach(() => {
    jest.clearAllTimers();
  });

  it('retries a transient failure up to maxAttempts and resolves on success', async () => {
    /**
     * WHY: Validates the primary acceptance criterion — transient errors
     * (e.g. 503 Service Unavailable) should be retried with backoff.
     * The task fails twice then succeeds on the third attempt.
     */
    const monitor = new JobMonitor<string>();
    const queue = new JobQueue<string>({
      monitor,
      policy: { maxAttempts: 3, baseDelayMs: 1 }, // tiny delay for tests
    });

    let callCount = 0;
    const task = jest.fn(async () => {
      callCount++;
      if (callCount < 3) throw new Error('503 Service Unavailable');
      return 'ok';
    });

    const promise = queue.enqueue(task);
    const result = await drainWithTimers(promise);

    expect(callCount).toBe(3);              // 2 retries occurred
    expect(result).toBe('ok');

    // Find the completed job in the monitor
    const monitor_ = queue.getMonitor();
    const dead = monitor_.getDeadJobs();
    expect(dead).toHaveLength(0);           // No dead jobs — it eventually succeeded
  });

  it('does NOT retry permanent (4xx) errors and marks job FAILED immediately', async () => {
    /**
     * WHY: Retrying a 401 Unauthorized or 400 Bad Request is wasteful and
     * will never succeed. The retry policy must short-circuit on permanent
     * errors to preserve resource budgets and avoid confusing log noise.
     */
    const onFailureMock = jest.fn();
    const onRetryMock = jest.fn();
    const monitor = new JobMonitor<string>({
      onFailure: onFailureMock,
      onRetry: onRetryMock,
    });
    const queue = new JobQueue<string>({
      monitor,
      policy: { maxAttempts: 3, baseDelayMs: 1 },
    });

    let callCount = 0;
    const task = jest.fn(async () => {
      callCount++;
      throw new Error('401 Unauthorized');
    });

    const promise = queue.enqueue(task);
    await expect(drainWithTimers(promise)).rejects.toThrow('401 Unauthorized');

    expect(callCount).toBe(1);             // Only one attempt — no retries
    expect(onRetryMock).not.toHaveBeenCalled();
    expect(onFailureMock).toHaveBeenCalledTimes(1);
    expect(onFailureMock.mock.calls[0][0]).toMatchObject({ status: 'FAILED', attempts: 1 });
  });

  it('moves job to dead-letter queue after all retry attempts are exhausted', async () => {
    /**
     * WHY: When a transient error persists across all retries the job must
     * be placed in the dead-letter queue so operators can inspect it and
     * decide on manual remediation without losing failure context.
     */
    const onDeadMock = jest.fn();
    const onRetryMock = jest.fn();
    const monitor = new JobMonitor<number>({
      onDead: onDeadMock,
      onRetry: onRetryMock,
    });
    const queue = new JobQueue<number>({
      monitor,
      policy: { maxAttempts: 3, baseDelayMs: 1 },
    });

    const task = jest.fn(async () => {
      throw new Error('Network timeout');
    });

    const promise = queue.enqueue(task);
    await expect(drainWithTimers(promise)).rejects.toThrow('Network timeout');

    expect(task).toHaveBeenCalledTimes(3); // All 3 attempts were made

    // onRetry fires after attempts 1 and 2 (not the final failure)
    expect(onRetryMock).toHaveBeenCalledTimes(2);

    // Job ends up in dead-letter state
    expect(onDeadMock).toHaveBeenCalledTimes(1);
    const deadJobs = monitor.getDeadJobs();
    expect(deadJobs).toHaveLength(1);
    expect(deadJobs[0].status).toBe('DEAD');
    expect(deadJobs[0].attempts).toBe(3);
    expect(deadJobs[0].error?.message).toBe('Network timeout');
  });
});

describe('defaultRetryPolicy.isRetryable', () => {
  it('treats 5xx and network errors as retryable', () => {
    expect(defaultRetryPolicy.isRetryable(new Error('500 Internal Server Error'))).toBe(true);
    expect(defaultRetryPolicy.isRetryable(new Error('503 Service Unavailable'))).toBe(true);
    expect(defaultRetryPolicy.isRetryable(new Error('Network timeout'))).toBe(true);
  });

  it('treats 4xx errors as permanent (not retryable)', () => {
    expect(defaultRetryPolicy.isRetryable(new Error('401 Unauthorized'))).toBe(false);
    expect(defaultRetryPolicy.isRetryable(new Error('400 Bad Request'))).toBe(false);
    expect(defaultRetryPolicy.isRetryable(new Error('403 Forbidden'))).toBe(false);
    expect(defaultRetryPolicy.isRetryable(new Error('404 Not Found'))).toBe(false);
  });
});
