import { api, baseURL } from './client';
import { getToken } from '@/lib/auth';

export type AuditLogEntry = {
  id: number;
  action: string;
  created_at: string;
};

/**
 * Trigger a full PII data export and download the resulting JSON file.
 * Uses raw fetch instead of the shared `api()` helper because we need
 * to handle the binary blob / Content-Disposition download ourselves.
 */
export async function exportData(): Promise<void> {
  const token = getToken();
  const res = await fetch(`${baseURL}/pii/export`, {
    method: 'GET',
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
    },
    credentials: 'include',
  });

  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const obj = JSON.parse(text) as { error?: string };
      msg = obj?.error || text;
    } catch {
      // not JSON
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }

  // Extract filename from Content-Disposition or use a fallback.
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] || 'finmind-data-export.json';

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 100);
}

/**
 * Permanently delete all user data.  Requires the confirmation phrase.
 */
export async function deleteData(
  confirm: string,
): Promise<{ message: string }> {
  return api<{ message: string }>('/pii/delete', {
    method: 'POST',
    body: { confirm },
  });
}

/**
 * Fetch the PII audit log entries for the current user.
 */
export async function getAuditLog(): Promise<AuditLogEntry[]> {
  return api<AuditLogEntry[]>('/pii/audit-log');
}
