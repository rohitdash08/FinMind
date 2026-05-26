import { api } from './client';

export type SecurityAlert = {
  id: number;
  login_event_id?: number | null;
  alert_type: 'new_ip' | 'new_device' | 'unusual_hour' | 'failed_login_burst';
  severity: 'medium' | 'high';
  message: string;
  details: {
    ip_address?: string;
    user_agent?: string;
    [key: string]: unknown;
  };
  acknowledged: boolean;
  created_at: string;
};

export type LoginEvent = {
  id: number;
  email: string;
  ip_address: string;
  user_agent: string;
  success: boolean;
  failure_reason?: string | null;
  is_suspicious: boolean;
  suspicion_reasons: string[];
  occurred_at: string;
};

export type LoginResponse = {
  access_token: string;
  refresh_token?: string;
  security_alerts?: SecurityAlert[];
};

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

export async function getLoginHistory(limit = 50): Promise<{ events: LoginEvent[] }> {
  return api<{ events: LoginEvent[] }>(`/auth/login-history?limit=${limit}`);
}

export async function getSecurityAlerts(
  limit = 50,
): Promise<{ alerts: SecurityAlert[]; unread_count: number }> {
  return api<{ alerts: SecurityAlert[]; unread_count: number }>(
    `/auth/security-alerts?limit=${limit}`,
  );
}

export async function acknowledgeSecurityAlert(
  alertId: number,
): Promise<SecurityAlert> {
  return api<SecurityAlert>(`/auth/security-alerts/${alertId}/acknowledge`, {
    method: 'POST',
  });
}
