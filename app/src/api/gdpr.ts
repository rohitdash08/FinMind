import { api } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExportPackage {
  export_generated_at: string;
  user: {
    id: number;
    email: string;
    preferred_currency: string;
    role: string;
    created_at: string | null;
  };
  categories: Record<string, unknown>[];
  expenses: Record<string, unknown>[];
  recurring_expenses: Record<string, unknown>[];
  bills: Record<string, unknown>[];
  reminders: Record<string, unknown>[];
  subscriptions: Record<string, unknown>[];
  audit_logs: Record<string, unknown>[];
}

export interface DeletionResponse {
  status: string;
  message: string;
  scheduled_at?: string;
  grace_period_days?: number;
}

export interface DeletionStatus {
  pending: boolean;
  scheduled_at?: string;
  requested_at?: string;
}

export interface AnonymizeResponse {
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Download all personal data as a JSON package. */
export async function exportData(): Promise<ExportPackage> {
  return api<ExportPackage>('/gdpr/export');
}

/** Request account deletion with a 30-day grace period. */
export async function requestDeletion(
  password: string,
  reason?: string,
): Promise<DeletionResponse> {
  return api<DeletionResponse>('/gdpr/delete', {
    method: 'POST',
    body: { password, reason },
  });
}

/** Cancel a pending deletion request. */
export async function cancelDeletion(): Promise<DeletionResponse> {
  return api<DeletionResponse>('/gdpr/delete/cancel', { method: 'POST' });
}

/** Confirm immediate, irreversible account deletion. */
export async function confirmDeletion(
  password: string,
): Promise<DeletionResponse> {
  return api<DeletionResponse>('/gdpr/delete/confirm', {
    method: 'POST',
    body: { password },
  });
}

/** Check whether a deletion request is pending. */
export async function deletionStatus(): Promise<DeletionStatus> {
  return api<DeletionStatus>('/gdpr/delete/status');
}

/** Anonymize personal data while keeping financial records. */
export async function anonymizeAccount(
  password: string,
): Promise<AnonymizeResponse> {
  return api<AnonymizeResponse>('/gdpr/anonymize', {
    method: 'POST',
    body: { password },
  });
}
