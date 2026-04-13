import { api } from './client';

export type ReminderMetrics = {
  total_sent: number;
  total_pending: number;
  delivery_rate: number;
  failed_count: number;
  avg_delay_seconds: number;
};

export type ReminderHistoryEntry = {
  id: number;
  message: string;
  send_at: string;
  sent: boolean;
  channel: 'email' | 'whatsapp';
  status: 'delivered' | 'pending' | 'failed';
};

export async function getReminderMetrics(): Promise<ReminderMetrics> {
  return api<ReminderMetrics>('/reminder-metrics');
}

export async function getReminderHistory(limit?: number): Promise<ReminderHistoryEntry[]> {
  const query = limit ? `?limit=${limit}` : '';
  return api<ReminderHistoryEntry[]>(`/reminder-metrics/history${query}`);
}
