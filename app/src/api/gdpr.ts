import { api } from './client';

export type ExportPackage = {
  exported_at: string;
  account: { email: string; preferred_currency: string; created_at: string };
  categories: { id: number; name: string }[];
  expenses: object[];
  bills: object[];
  reminders: object[];
};

export type DeletionRequestResponse = {
  message: string;
  confirmation_token: string;
  grace_period_ends_at: string;
  grace_period_days: number;
};

export type DeletionStatus = {
  status: string | null;
  message?: string;
  created_at?: string;
  grace_period_ends_at?: string;
  confirmed_at?: string | null;
  completed_at?: string | null;
};

export type AuditEntry = {
  id: number;
  action: string;
  details: object;
  ip_address: string | null;
  created_at: string;
};

export async function exportPII(): Promise<ExportPackage> {
  return api<ExportPackage>('/gdpr/export', { method: 'POST' });
}

export async function requestDeletion(reason?: string): Promise<DeletionRequestResponse> {
  return api<DeletionRequestResponse>('/gdpr/delete', {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export async function confirmDeletion(token: string): Promise<{ message: string; deleted_at: string }> {
  return api('/gdpr/delete/confirm', {
    method: 'POST',
    body: JSON.stringify({ confirmation_token: token }),
  });
}

export async function cancelDeletion(): Promise<{ message: string }> {
  return api('/gdpr/delete/cancel', { method: 'POST' });
}

export async function getDeletionStatus(): Promise<DeletionStatus> {
  return api<DeletionStatus>('/gdpr/delete/status');
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  return api<AuditEntry[]>('/gdpr/audit');
}
