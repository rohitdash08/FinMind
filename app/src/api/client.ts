import {
  getToken,
  setToken,
  clearToken,
  getRefreshToken,
  clearRefreshToken,
} from '../lib/auth';
import { refresh as refreshApi } from './auth';
import {
  withRetry,
  computeDelay,
  defaultShouldRetry,
  type RetryConfig,
} from '../lib/retry';
import * as monitor from '../lib/request-monitor';

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

export interface ApiOptions {
  method?: HttpMethod;
  body?: unknown;
  headers?: Record<string, string>;
  /** Override retry configuration. Pass `false` to disable retries. */
  retry?: Partial<RetryConfig> | false;
}

/**
 * Core API function with automatic retry + request monitoring.
 *
 * Retries are enabled by default for network failures and 5xx/429 responses.
 * Pass `retry: false` to disable, or supply partial overrides.
 */
export async function api<T = unknown>(
  path: string,
  opts: ApiOptions = {},
): Promise<T> {
  const retryCfg = opts.retry === false
    ? false
    : { maxAttempts: 3, baseDelayMs: 500, maxDelayMs: 10_000, jitterFactor: 0.5, ...opts.retry };

  const method = opts.method || 'GET';
  const maxAttempts = retryCfg ? retryCfg.maxAttempts : 0;
  const reqId = monitor.beginRequest(path, method, maxAttempts);

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

  /** Core single-attempt fetch with auth-refresh logic. */
  async function executeOnce(): Promise<T> {
    let res = await doFetch(true);

    // Attempt refresh once on 401
    if (res.status === 401 && path !== '/auth/refresh' && path !== '/auth/logout') {
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

    if (!res.ok) {
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
      throw new Error(msg || `HTTP ${res.status}`);
    }

    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      return (await res.json()) as T;
    }
    return (await res.text()) as unknown as T;
  }

  try {
    if (retryCfg === false) {
      // No retry – just run once.
      const result = await executeOnce();
      monitor.markSuccess(reqId);
      return result;
    }

    // Wrap with retry. Use the monitor hooks for visibility.
    const result = await withRetry(executeOnce, {
      ...retryCfg,
      onRetry(attempt, delayMs, error) {
        const errMsg = error instanceof Error ? error.message : String(error);
        monitor.markRetry(reqId, attempt, errMsg);
        retryCfg.onRetry?.(attempt, delayMs, error);
      },
    });
    monitor.markSuccess(reqId);
    return result;
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    monitor.markFailed(reqId, errMsg);
    throw err;
  }
}
