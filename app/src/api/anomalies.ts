import { api } from './client';

export type AnomalyAlert = {
  id: number; alert_type: string; severity: string;
  message: string; expense_id: number | null;
  acknowledged: boolean; created_at: string;
};

export type ScanResult = { alerts_created: number; alerts: AnomalyAlert[] };

export async function listAlerts(unacknowledged?: boolean): Promise<AnomalyAlert[]> {
  const q = unacknowledged ? '?unacknowledged=true' : '';
  return api<AnomalyAlert[]>('/anomalies' + q);
}

export async function acknowledgeAlert(id: number): Promise<AnomalyAlert> {
  return api<AnomalyAlert>('/anomalies/' + id + '/acknowledge', { method: 'POST' });
}

export async function scanAnomalies(): Promise<ScanResult> {
  return api<ScanResult>('/anomalies/scan', { method: 'POST' });
}
