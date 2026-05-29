import { api, baseURL } from './client';
import { getToken } from '../lib/auth';

export type LoginResponse = { access_token: string; refresh_token?: string };

export async function login(email: string, password: string): Promise<LoginResponse> {
  return api<LoginResponse>('/auth/login', { method: 'POST', body: { email, password } });
}

export async function register(email: string, password: string): Promise<{ message: string } | LoginResponse> {
  return api('/auth/register', { method: 'POST', body: { email, password } });
}

export type RefreshResponse = { access_token: string };
export async function refresh(refresh_token: string): Promise<RefreshResponse> {
  return api<RefreshResponse>('/auth/refresh', {
    method: 'POST',
    headers: { Authorization: `Bearer ${refresh_token}` },
  });
}

export async function logout(refresh_token: string): Promise<{ message: string }> {
  return api<{ message: string }>('/auth/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${refresh_token}` },
  });
}

export type MeResponse = { id: number; email: string; preferred_currency: string };
export async function me(): Promise<MeResponse> {
  return api<MeResponse>('/auth/me');
}

export async function updateMe(payload: {
  preferred_currency: string;
}): Promise<MeResponse> {
  return api<MeResponse>('/auth/me', { method: 'PATCH', body: payload });
}

export async function exportPrivacyData(): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${baseURL}/privacy/export`, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const payload = (await res.json()) as { error?: string; message?: string };
      message = payload.error || payload.message || message;
    } catch {
      // Keep status-based fallback for non-JSON failures.
    }
    throw new Error(message);
  }
  return res.blob();
}

export async function deleteAccount(confirm: string): Promise<{
  message: string;
  deleted_records: Record<string, number>;
  anonymized_audit_logs: number;
  deleted_cache_keys: number;
  revoked_refresh_sessions: number;
}> {
  return api('/privacy/me', {
    method: 'DELETE',
    body: { confirm },
  });
}
