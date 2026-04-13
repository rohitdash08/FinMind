import { api } from './client';

export type ExportSummary = {
  profile: number;
  expenses: number;
  categories: number;
  bills: number;
  reminders: number;
  recurring_expenses: number;
};

export type ExportResult = {
  json_data: string;
  csv_data: string;
  summary: ExportSummary;
};

export type DeleteResult = {
  message: string;
  deleted: Record<string, number>;
};

export type AuditEntry = {
  id: number;
  action: string;
  created_at: string;
};

export async function exportData(): Promise<ExportResult> {
  return api<ExportResult>('/privacy/export');
}

export async function deleteAllData(): Promise<DeleteResult> {
  return api<DeleteResult>('/privacy/delete', { method: 'POST', body: { confirm: true } });
}

export async function getAuditLog(): Promise<AuditEntry[]> {
  return api<AuditEntry[]>('/privacy/audit-log');
}
