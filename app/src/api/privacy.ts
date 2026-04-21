import { api } from './client';

export type PrivacyExportPackage = {
  generated_at: string;
  user: {
    id: number;
    email: string;
    preferred_currency: string;
    role: string;
    created_at: string;
  };
  categories: unknown[];
  expenses: unknown[];
  recurring_expenses: unknown[];
  bills: unknown[];
  reminders: unknown[];
  subscriptions: unknown[];
  ad_impressions: unknown[];
  audit_logs: unknown[];
};

export async function exportPersonalData(): Promise<PrivacyExportPackage> {
  return api<PrivacyExportPackage>('/privacy/export');
}

export async function deletePersonalData(): Promise<{ message: string }> {
  return api<{ message: string }>('/privacy/delete', {
    method: 'DELETE',
    body: { confirmation: 'DELETE' },
  });
}
