import {
  getToken,
  setToken,
  clearToken,
  getRefreshToken,
  clearRefreshToken,
} from '../lib/auth';
import { refresh as refreshApi } from './auth';

function resolveApiBaseUrl(): string {
  const fromRuntime = (globalThis as { __FINMIND_API_URL__?: string }).__FINMIND_API_URL__;
  if (fromRuntime) return fromRuntime.replace(/\/$/, '');

  const fromProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process?.env?.VITE_API_URL;
  if (fromProcess) return fromProcess.replace(/\/$/, '');

  try {
    const metaEnv = Function(
      'return (typeof import !== "undefined" && import.meta && import.meta.env) ? import.meta.env : {};',
    )() as Record<string, string | undefined>;
    if (metaEnv?.VITE_API_URL) return metaEnv.VITE_API_URL.replace(/\/$/, '');
  } catch {
    // ignored for non-vite runtime (tests).
  }
  return 'http://localhost:8000';
}

export const baseURL = resolveApiBaseUrl();

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

/** Retry configuration for resilient API calls. */
export interface RetryConfig {
  /** Maximum number of retry attempts (default: 3). */
  maxRetries: number;
  /** Base delay in ms for exponential backoff (default: 500). */
  baseDelayMs: number;
  /** Maximum delay in ms between retries (default: 10000). */
  maxDelayMs: number;
  /** HTTP status codes that should trigger a retry (default: [408, 429, 500, 502, 503, 504]). */
  retryableStatuses: number[];
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 10_000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

/** Metrics emitted for each API call attempt. */
export interface ApiCallMetric {
  path: string;
  method: string;
  attempt: number;
  status: number;
  durationMs: number;
  retried: boolean;
  error?: string;
}

type MetricListener = (metric: ApiCallMetric) => void;
const metricListeners: MetricListener[] = [];

/** Register a listener to receive API call metrics (for monitoring). */
export function onApiMetric(listener: MetricListener): () => void {
  metricListeners.push(listener);
  return () => {
    const idx = metricListeners.indexOf(listener);
    if (idx >= 0) metricListeners.splice(idx, 1);
  };
}

function emitMetric(metric: ApiCallMetric): void {
  for (const fn of metricListeners) {
    try {
      fn(metric);
    } catch {
      // listener errors should not break the chain
    }
  }
}

function shouldRetryStatus(status: number, config: RetryConfig): boolean {
  return config.retryableStatuses.includes(status);
}

/** Compute backoff delay with jitter for the given attempt (0-indexed). */
export function computeBackoffMs(attempt: number, config: RetryConfig): number {
  const exp = Math.min(config.baseDelayMs * 2 ** attempt, config.maxDelayMs);
  // Add ±25 % jitter to avoid thundering herd.
  const jitter = exp * (0.75 + Math.random() * 0.5);
  return Math.round(jitter);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: HttpMethod; body?: unknown; headers?: Record<string, string> } = {},
  retryConfig?: Partial<RetryConfig>,
): Promise<T> {
  const config: RetryConfig = { ...DEFAULT_RETRY_CONFIG, ...retryConfig };
  const method = opts.method || 'GET';

  async function doFetch(withAuth = true): Promise<Response> {
    const token = withAuth ? getToken() : null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(`${baseURL}${path}`, {
      method,
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: 'include',
    });
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    const startTime = performance.now();
    let res: Response;
    try {
      res = await doFetch(true);
    } catch (networkError) {
      const durationMs = Math.round(performance.now() - startTime);
      const err = networkError instanceof Error ? networkError : new Error(String(networkError));
      emitMetric({ path, method, attempt: attempt + 1, status: 0, durationMs, retried: attempt < config.maxRetries, error: err.message });

      // Network errors are retryable
      if (attempt < config.maxRetries) {
        await sleep(computeBackoffMs(attempt, config));
        continue;
      }
      throw err;
    }

    // Attempt refresh once on 401 (only on first attempt to avoid loops)
    if (res.status === 401 && path !== '/auth/refresh' && path !== '/auth/logout' && attempt === 0) {
      const rt = getRefreshToken();
      if (rt) {
        try {
          const r = await refreshApi(rt);
          setToken(r.access_token);
          res = await doFetch(true);
        } catch {
          clearToken();
          clearRefreshToken();
          throw new Error('Unauthorized');
        }
      } else {
        clearToken();
        clearRefreshToken();
        throw new Error('Unauthorized');
      }
    }

    const durationMs = Math.round(performance.now() - startTime);

    if (res.ok) {
      emitMetric({ path, method, attempt: attempt + 1, status: res.status, durationMs, retried: attempt > 0 });
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        return (await res.json()) as T;
      }
      return (await res.text()) as unknown as T;
    }

    // Retryable server errors
    if (shouldRetryStatus(res.status, config) && attempt < config.maxRetries) {
      emitMetric({ path, method, attempt: attempt + 1, status: res.status, durationMs, retried: true });
      await sleep(computeBackoffMs(attempt, config));
      continue;
    }

    // Non-retryable error — parse and throw
    emitMetric({ path, method, attempt: attempt + 1, status: res.status, durationMs, retried: false });
    const text = await res.text();
    let msg = text;
    const contentType = res.headers.get('content-type') || '';
    try {
      const obj = JSON.parse(text) as { error?: string; message?: string };
      msg = (obj && (obj.error || obj.message)) || JSON.stringify(obj);
    } catch {
      if (contentType.includes('text/html') || /<!doctype html>/i.test(text)) {
        if (res.status >= 500) {
          msg = 'Server error. Please try again in a minute.';
        } else {
          msg = 'Request failed. Please try again.';
        }
      } else {
        msg = text || `HTTP ${res.status}`;
      }
    }
    if (!msg) msg = `HTTP ${res.status}`;
    lastError = new Error(msg || `HTTP ${res.status}`);
    throw lastError;
  }

  // Should not reach here, but just in case
  throw lastError ?? new Error(`Request failed after ${config.maxRetries + 1} attempts`);
}
