import { api } from './client';

export type PersonalDataExport = {
  generated_at: string;
  user: {
    id: number;
    email: string;
    preferred_currency: string;
    role: string;
    created_at: string;
  };
  categories: Record<string, unknown>[];
  expenses: Record<string, unknown>[];
  recurring_expenses: Record<string, unknown>[];
  bills: Record<string, unknown>[];
  reminders: Record<string, unknown>[];
  subscriptions: Record<string, unknown>[];
  audit_logs: Record<string, unknown>[];
};

export async function exportPersonalData(): Promise<PersonalDataExport> {
  return api<PersonalDataExport>('/privacy/export');
}

export async function deletePersonalData(password: string): Promise<{ message: string }> {
  return api<{ message: string }>('/privacy/delete', {
    method: 'POST',
    body: { password },
  });
}
