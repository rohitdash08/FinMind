import { api } from './client';

export type PIIExport = {
  export_version: string;
  exported_at: string;
  profile: {
    id: number;
    email: string;
    preferred_currency: string;
    role: string;
    created_at: string;
  };
  categories: Array<{ id: number; name: string; created_at: string }>;
  expenses: Array<{
    id: number;
    amount: number;
    currency: string;
    expense_type: string;
    notes: string | null;
    spent_at: string;
    category_id: number | null;
    created_at: string;
  }>;
  recurring_expenses: Array<Record<string, unknown>>;
  bills: Array<Record<string, unknown>>;
  reminders: Array<Record<string, unknown>>;
  subscriptions: Array<Record<string, unknown>>;
  audit_logs: Array<Record<string, unknown>>;
};

export async function exportPII(): Promise<PIIExport> {
  return api<PIIExport>('/privacy/export');
}

export async function deletePII(): Promise<{ message: string }> {
  return api<{ message: string }>('/privacy/delete', {
    method: 'POST',
    body: { confirm: true },
  });
}
