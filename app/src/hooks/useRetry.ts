import { useCallback, useRef, useState } from 'react';
import { computeBackoffMs, type RetryConfig } from '@/api/client';

const DEFAULT_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 10_000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

export interface UseRetryOptions {
  /** Override default retry configuration. */
  config?: Partial<RetryConfig>;
  /** Called when a retry is about to happen. */
  onRetry?: (attempt: number, error: unknown) => void;
  /** Called when all retries are exhausted. */
  onFailure?: (error: unknown) => void;
  /** Called on eventual success after retries. */
  onSuccess?: () => void;
}

export interface UseRetryReturn<T> {
  /** Execute the async function with automatic retries. */
  execute: () => Promise<T>;
  /** Whether the function is currently running. */
  loading: boolean;
  /** The last error encountered (if any). */
  error: unknown;
  /** Number of retry attempts made so far. */
  attempts: number;
  /** Reset the state. */
  reset: () => void;
}

/**
 * Hook that wraps an async function with exponential-backoff retry logic.
 *
 * ```tsx
 * const { execute, loading, error, attempts } = useRetry(
 *   () => fetchImportantData(),
 *   { onRetry: (n) => console.log(`retry #${n}`) },
 * );
 * ```
 */
export function useRetry<T>(
  fn: () => Promise<T>,
  options: UseRetryOptions = {},
): UseRetryReturn<T> {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempts, setAttempts] = useState(0);
  const cancelledRef = useRef(false);

  const config: RetryConfig = { ...DEFAULT_CONFIG, ...options.config };

  const execute = useCallback(async (): Promise<T> => {
    cancelledRef.current = false;
    setLoading(true);
    setError(null);
    setAttempts(0);

    let lastError: unknown;

    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      if (cancelledRef.current) {
        throw new Error('Cancelled');
      }

      try {
        const result = await fn();
        setLoading(false);
        setAttempts(attempt);
        options.onSuccess?.();
        return result;
      } catch (err) {
        lastError = err;
        setAttempts(attempt + 1);

        if (attempt < config.maxRetries) {
          options.onRetry?.(attempt + 1, err);
          const delay = computeBackoffMs(attempt, config);
          await new Promise<void>((resolve) => setTimeout(resolve, delay));
        }
      }
    }

    setError(lastError);
    setLoading(false);
    options.onFailure?.(lastError);
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }, [fn, config, options]);

  const reset = useCallback(() => {
    cancelledRef.current = true;
    setLoading(false);
    setError(null);
    setAttempts(0);
  }, []);

  return { execute, loading, error, attempts, reset };
}
