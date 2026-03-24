import { api } from './client';

export interface LoginAlert {
  id: number;
  alert_type: string;
  severity: string;
  message: string;
  read: boolean;
  created_at: string;
}

export interface AlertsResponse {
  alerts: LoginAlert[];
}

export interface UnreadCountResponse {
  unread_count: number;
}

export async function getAlerts(unread = false, limit = 50): Promise<AlertsResponse> {
  const params = new URLSearchParams();
  if (unread) params.set('unread', 'true');
  params.set('limit', String(limit));
  return api<AlertsResponse>(`/alerts/?${params.toString()}`);
}

export async function getUnreadCount(): Promise<UnreadCountResponse> {
  return api<UnreadCountResponse>('/alerts/unread-count');
}

export async function markAlertsRead(alertIds?: number[]): Promise<{ marked_read: number }> {
  return api('/alerts/read', {
    method: 'POST',
    body: alertIds ? { alert_ids: alertIds } : {},
  });
}
