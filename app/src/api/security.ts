import { api } from './client';

export interface LoginEvent {
  id: number;
  ip_address: string | null;
  user_agent: string | null;
  success: boolean;
  anomaly_score: number;
  anomaly_reasons: string | null;
  created_at: string;
}

export interface LoginStats {
  total_logins: number;
  unique_ips: number;
  unique_devices: number;
  suspicious_count: number;
  last_anomaly: string | null;
}

export async function getLoginHistory(limit = 50): Promise<LoginEvent[]> {
  return api<LoginEvent[]>(`/security/login-history?limit=${limit}`);
}

export async function getAnomalies(limit = 50): Promise<LoginEvent[]> {
  return api<LoginEvent[]>(`/security/anomalies?limit=${limit}`);
}

export async function getLoginStats(): Promise<LoginStats> {
  return api<LoginStats>('/security/login-stats');
}
