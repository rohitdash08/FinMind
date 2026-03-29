import { api } from './client';

export type Reminder = {
  id: number;
  message: string;
  send_at: string; // ISO datetime
  sent: boolean;
  channel: 'email' | 'whatsapp';
  // Delivery tracking fields
  delivered?: boolean;
  delivery_attempts: number;
  last_attempt_at?: string;
  error_message?: string;
};

export type ReminderCreate = {
  message: string;
  send_at: string; // ISO datetime
  channel?: 'email' | 'whatsapp';
};

export type ReminderUpdate = Partial<ReminderCreate>;

export type ReminderDelivery = {
  id: number;
  attempted_at: string;
  success: boolean;
  channel: string;
  error_message?: string;
  response_time_ms?: number;
};

export type DeliveryMetrics = {
  period_days: number;
  total_attempts: number;
  successful_deliveries: number;
  failed_deliveries: number;
  success_rate: number;
  average_response_time_ms: number;
  by_channel?: {
    email: {
      attempts: number;
      successful: number;
      success_rate: number;
    };
    whatsapp: {
      attempts: number;
      successful: number;
      success_rate: number;
    };
  };
};

export type RunDueResult = {
  processed: number;
  delivered: number;
  failed: number;
};

export type RetryResult = {
  success: boolean;
  delivered?: boolean;
  attempts: number;
};

export async function listReminders(): Promise<Reminder[]> {
  return api<Reminder[]>('/reminders');
}

export async function createReminder(payload: ReminderCreate): Promise<Reminder> {
  return api<Reminder>('/reminders', { method: 'POST', body: payload });
}

export async function updateReminder(id: number, payload: ReminderUpdate): Promise<Reminder> {
  return api<Reminder>(`/reminders/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteReminder(id: number): Promise<{ message?: string }> {
  return api(`/reminders/${id}`, { method: 'DELETE' });
}

export async function runDue(): Promise<RunDueResult> {
  return api<RunDueResult>('/reminders/run', { method: 'POST' });
}

// New delivery tracking APIs

export async function getDeliveryMetrics(days?: number): Promise<DeliveryMetrics> {
  const query = days ? `?days=${days}` : '';
  return api<DeliveryMetrics>(`/reminders/metrics${query}`);
}

export async function getFailedReminders(): Promise<Reminder[]> {
  return api<Reminder[]>('/reminders/failed');
}

export async function retryReminder(id: number): Promise<RetryResult> {
  return api<RetryResult>(`/reminders/${id}/retry`, { method: 'POST' });
}

export async function getReminderDeliveries(id: number): Promise<ReminderDelivery[]> {
  return api<ReminderDelivery[]>(`/reminders/${id}/deliveries`);
}

export async function scheduleBillReminders(
  billId: number,
  offsetsDays?: number[],
): Promise<{ created: number }> {
  return api<{ created: number }>(`/reminders/bills/${billId}/schedule`, {
    method: 'POST',
    body: offsetsDays && offsetsDays.length > 0 ? { offsets_days: offsetsDays } : {},
  });
}

export async function reportAutopayResult(
  billId: number,
  status: 'SUCCESS' | 'FAILED',
): Promise<{ created: number }> {
  return api<{ created: number }>(`/reminders/bills/${billId}/autopay-result`, {
    method: 'POST',
    body: { status },
  });
}
