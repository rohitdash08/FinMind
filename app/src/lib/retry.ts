/**
 * Resilient retry utilities with exponential backoff, jitter, and
 * configurable retry budgets.
 */

/** Retryable HTTP status codes (server errors + rate-limit). */
export const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

export interface RetryConfig {
  /** Maximum number of retry attempts (default 3). */
  maxAttempts: number;
  /** Base delay in ms before first retry (default 500). */
  baseDelayMs: number;
  /** Maximum delay cap in ms (default 10_000). */
  maxDelayMs: number;
  /** Jitter factor 0-1 (default 0.5). */
  jitterFactor: number;
  /** Optional predicate – return true to retry. */
  shouldRetry?: (error: unknown, attempt: number) => boolean;
  /** Called before each retry attempt. */
  onRetry?: (attempt: number, delayMs: number, error: unknown) => void;
}

const DEFAULT_CONFIG: RetryConfig = {
  maxAttempts: 3,
  baseDelayMs: 500,
  maxDelayMs: 10_000,
  jitterFactor: 0.5,
};

/**
 * Compute exponential-backoff delay with jitter.
 *
 * ```
 * delay = min(baseDelay * 2^attempt, maxDelay)
 * delay = delay * (1 + random(-jitter, jitter))
 * ```
 */
export function computeDelay(attempt: number, cfg: RetryConfig): number {
  const exponential = Math.min(cfg.baseDelayMs * 2 ** attempt, cfg.maxDelayMs);
  const jitter = exponential * cfg.jitterFactor * (Math.random() * 2 - 1);
  return Math.max(0, Math.round(exponential + jitter));
}

/** Default shouldRetry: network errors + retryable HTTP statuses. */
export function defaultShouldRetry(error: unknown, _attempt: number): boolean {
  if (error instanceof TypeError) {
    // fetch() throws TypeError on network failure
    return true;
  }
  if (error instanceof Error) {
    const statusMatch = error.message.match(/HTTP (\d+)/);
    if (statusMatch) {
      return RETRYABLE_STATUSES.has(Number(statusMatch[1]));
    }
  }
  return false;
}

/**
 * Wrap an async function with retry logic.
 *
 * ```ts
 * const data = await withRetry(() => api('/dashboard/summary'), { maxAttempts: 5 });
 * ```
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  overrides?: Partial<RetryConfig>,
): Promise<T> {
  const cfg: RetryConfig = { ...DEFAULT_CONFIG, ...overrides };
  let lastError: unknown;

  for (let attempt = 0; attempt <= cfg.maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      const shouldRetry = cfg.shouldRetry ?? defaultShouldRetry;

      if (attempt >= cfg.maxAttempts || !shouldRetry(err, attempt)) {
        throw err;
      }

      const delayMs = computeDelay(attempt, cfg);
      cfg.onRetry?.(attempt + 1, delayMs, err);
      await sleep(delayMs);
    }
  }

  throw lastError;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
