import { api, baseURL } from './client';
import { getToken } from '../lib/auth';

// --- Types ---

export type DataRequestType = 'EXPORT' | 'DELETE';
export type DataRequestStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface DataRequestItem {
  id: number;
  request_type: DataRequestType;
  status: DataRequestStatus;
  has_download: boolean;
  expires_at: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface ExportResponse {
  request_id: number;
  status: string;
  message: string;
}

export interface DeleteRequestResponse {
  request_id: number;
  confirmation_token: string;
  message: string;
}

export interface DeleteConfirmResponse {
  request_id: number;
  status: string;
  message: string;
}

// --- API functions ---

export async function requestExport(): Promise<ExportResponse> {
  return api<ExportResponse>('/privacy/export', { method: 'POST' });
}

export async function downloadExport(requestId: number): Promise<void> {
  const token = getToken();
  const res = await fetch(`${baseURL}/privacy/export/${requestId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const obj = JSON.parse(text) as { error?: string };
      msg = obj?.error || text;
    } catch {
      // use raw text
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `finmind-data-export.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function listDataRequests(): Promise<DataRequestItem[]> {
  return api<DataRequestItem[]>('/privacy/requests');
}

export async function requestDeletion(): Promise<DeleteRequestResponse> {
  return api<DeleteRequestResponse>('/privacy/delete', { method: 'POST' });
}

export async function confirmDeletion(
  requestId: number,
  confirmationToken: string,
): Promise<DeleteConfirmResponse> {
  return api<DeleteConfirmResponse>('/privacy/delete/confirm', {
    method: 'POST',
    body: { request_id: requestId, confirmation_token: confirmationToken },
  });
}
