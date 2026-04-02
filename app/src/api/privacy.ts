import { api, baseURL } from './client';
import { getToken } from '@/lib/auth';

export type AuditEntry = {
  user_id: number;
  action: string;
  ip: string;
  timestamp: string;
};

export async function requestExport(): Promise<{ job_id: string; status: string }> {
  return api('/privacy/export', { method: 'POST' });
}

export async function downloadExport(jobId: string): Promise<void> {
  const res = await fetch(`${baseURL}/privacy/export/${jobId}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({})) as { status?: string };
    if (data.status === 'pending') throw new Error('Export still processing');
    throw new Error('Export not ready');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'finmind-export.zip';
  a.click();
  URL.revokeObjectURL(url);
}

export async function deleteAccount(confirmation: string): Promise<{ message: string }> {
  return api('/privacy/account', { method: 'DELETE', body: { confirmation } });
}

export async function getAuditLog(): Promise<AuditEntry[]> {
  return api<AuditEntry[]>('/privacy/audit');
}
