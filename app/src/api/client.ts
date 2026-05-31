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

export async function api<T = unknown>(
  path: string,
  opts: { method?: HttpMethod; body?: unknown; headers?: Record<string, string> } = {},
): Promise<T> {
  async function doFetch(withAuth = true): Promise<Response> {
    const token = withAuth ? getToken() : null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(`${baseURL}${path}`, {
      method: opts.method || 'GET',
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: 'include',
    });
  }

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
