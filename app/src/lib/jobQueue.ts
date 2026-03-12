/**
 * jobQueue.ts
 *
 * Resilient background job queue with exponential backoff retry and monitoring.
 *
 * WHY: Issue #130 requires production-ready async job execution with retry logic
 * and monitoring hooks. This module provides a reusable JobQueue and JobMonitor
 * that wraps any async function, retries transient failures with exponential
 * backoff, and emits lifecycle events for observability.
 */

export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'DEAD';

export interface JobRecord<T> {
  id: string;
  status: JobStatus;
  result?: T;
  error?: Error;
  attempts: number;
  createdAt: number;
  updatedAt: number;
}

export interface RetryPolicy {
  /** Maximum number of total attempts (1 = no retries). Default: 3 */
  maxAttempts: number;
  /** Base delay in ms for exponential backoff. Default: 200 */
  baseDelayMs: number;
  /**
   * Predicate to decide if an error is retryable.
   * WHY: We must NOT retry permanent errors (401 auth, 400 bad request)
   * because retrying them wastes resources and will never succeed.
   * Only transient errors (5xx, network timeouts) should be retried.
   */
  isRetryable: (error: Error) => boolean;
}

export interface MonitorHooks<T> {
  onSuccess?: (job: JobRecord<T>) => void;
  onFailure?: (job: JobRecord<T>, error: Error) => void;
  onRetry?: (job: JobRecord<T>, attempt: number, error: Error) => void;
  onDead?: (job: JobRecord<T>) => void;
}

/** Default retry policy: retry up to 3 attempts, skip 4xx errors. */
export const defaultRetryPolicy: RetryPolicy = {
  maxAttempts: 3,
  baseDelayMs: 200,
  isRetryable: (error: Error) => {
    // WHY: HTTP 4xx errors are client errors and will never succeed on retry.
    // We check the message for status codes as a pragmatic heuristic since
    // we don't have a typed HttpError in the current API layer.
    const msg = error.message ?? '';
    const permanentPattern = /\b4\d{2}\b/;
    return !permanentPattern.test(msg);
  },
};

/**
 * Generates a short unique ID for each job.
 * WHY: Jobs need stable IDs so monitors and callers can correlate records
 * across async boundaries without external libraries.
 */
function generateId(): string {
  return `job_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Returns a promise that resolves after `ms` milliseconds.
 * WHY: We need a controllable delay for exponential backoff between retries.
 * Using jest.useFakeTimers in tests allows us to fast-forward time.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * JobMonitor
 *
 * Stores job records and exposes query helpers + lifecycle hooks.
 * WHY: Separating monitoring from execution keeps the queue logic
 * focused on retry mechanics while the monitor handles observability.
 * Callers can attach hooks for metrics, alerting, or dead-letter processing.
 */
export class JobMonitor<T = unknown> {
  private records = new Map<string, JobRecord<T>>();
  private hooks: MonitorHooks<T>;

  constructor(hooks: MonitorHooks<T> = {}) {
    this.hooks = hooks;
  }

  /** @internal Called by JobQueue to register a new job. */
  _register(id: string): JobRecord<T> {
    const record: JobRecord<T> = {
      id,
      status: 'PENDING',
      attempts: 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    this.records.set(id, record);
    return record;
  }

  /** @internal Called by JobQueue on each attempt start. */
  _markRunning(id: string): void {
    const r = this._get(id);
    r.status = 'RUNNING';
    r.attempts += 1;
    r.updatedAt = Date.now();
  }

  /** @internal Called by JobQueue on successful completion. */
  _markCompleted(id: string, result: T): void {
    const r = this._get(id);
    r.status = 'COMPLETED';
    r.result = result;
    r.updatedAt = Date.now();
    this.hooks.onSuccess?.(r);
  }

  /** @internal Called by JobQueue when a retryable error occurs. */
  _markRetrying(id: string, error: Error): void {
    const r = this._get(id);
    r.error = error;
    r.updatedAt = Date.now();
    this.hooks.onRetry?.(r, r.attempts, error);
  }

  /** @internal Called by JobQueue on non-retryable or final failure. */
  _markFailed(id: string, error: Error, dead: boolean): void {
    const r = this._get(id);
    r.status = dead ? 'DEAD' : 'FAILED';
    r.error = error;
    r.updatedAt = Date.now();
    if (dead) {
      this.hooks.onDead?.(r);
    } else {
      this.hooks.onFailure?.(r, error);
    }
  }

  /** Returns the current status of a job by ID. */
  getJobStatus(id: string): JobStatus | undefined {
    return this.records.get(id)?.status;
  }

  /** Returns the full job record for a given ID. */
  getJob(id: string): JobRecord<T> | undefined {
    return this.records.get(id);
  }

  /**
   * Returns all jobs that reached the DEAD status.
   * WHY: Dead-letter queue pattern — callers can inspect permanently failed
   * jobs for manual intervention or alerting without losing the history.
   */
  getDeadJobs(): JobRecord<T>[] {
    return Array.from(this.records.values()).filter((r) => r.status === 'DEAD');
  }

  /**
   * Clears all stored records.
   * WHY: Prevents unbounded memory growth in long-running processes.
   * Callers should periodically flush old records or call this on cleanup.
   */
  clear(): void {
    this.records.clear();
  }

  private _get(id: string): JobRecord<T> {
    const r = this.records.get(id);
    if (!r) throw new Error(`JobMonitor: unknown job id "${id}"`);
    return r;
  }
}

/**
 * JobQueue
 *
 * Enqueues async tasks and executes them with retry + monitoring.
 *
 * Usage:
 * ```ts
 * const monitor = new JobMonitor({ onSuccess: (job) => console.log('done', job.id) });
 * const queue = new JobQueue({ monitor });
 *
 * const result = await queue.enqueue(() => api.getDashboardSummary({ month: '2026-02' }));
 * ```
 */
export class JobQueue<T = unknown> {
  private policy: RetryPolicy;
  private monitor: JobMonitor<T>;

  constructor(options: { policy?: Partial<RetryPolicy>; monitor?: JobMonitor<T> } = {}) {
    this.policy = { ...defaultRetryPolicy, ...options.policy };
    // WHY: Allow callers to share a monitor across multiple queues for
    // centralised observability, or use an isolated monitor per queue.
    this.monitor = options.monitor ?? new JobMonitor<T>();
  }

  /**
   * Enqueues a task and returns a promise that resolves with the result
   * or rejects after all retry attempts are exhausted.
   *
   * @param task - A zero-argument function returning a Promise<T>.
   * @returns Promise<T> resolved when the task succeeds.
   */
  async enqueue(task: () => Promise<T>): Promise<T> {
    const id = generateId();
    this.monitor._register(id);

    const { maxAttempts, baseDelayMs, isRetryable } = this.policy;

    let lastError: Error = new Error('Unknown error');

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      this.monitor._markRunning(id);

      try {
        const result = await task();
        this.monitor._markCompleted(id, result);
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));

        const isLast = attempt === maxAttempts;
        const canRetry = isRetryable(lastError);

        if (!canRetry) {
          // WHY: Permanent errors (e.g. 401) should fail immediately rather
          // than wasting attempts that will also fail for the same reason.
          this.monitor._markFailed(id, lastError, false);
          throw lastError;
        }

        if (isLast) {
          // WHY: Job goes to DEAD state when all retries are exhausted,
          // enabling dead-letter inspection without losing failure context.
          this.monitor._markFailed(id, lastError, true);
          throw lastError;
        }

        this.monitor._markRetrying(id, lastError);

        // Exponential backoff: 200ms, 400ms, 800ms, …
        // WHY: Immediate retries can overwhelm a struggling service.
        // Exponential backoff gives the dependency time to recover.
        const delay = baseDelayMs * Math.pow(2, attempt - 1);
        await sleep(delay);
      }
    }

    // Unreachable but satisfies TypeScript's control-flow analysis.
    throw lastError;
  }

  /** Exposes the underlying monitor for status queries. */
  getMonitor(): JobMonitor<T> {
    return this.monitor;
  }
}
