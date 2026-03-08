import { baseURL } from './client';
import { getToken } from '../lib/auth';

/**
 * Download user data export as a ZIP file.
 */
export async function exportUserData(): Promise<Blob> {
  const res = await fetch(`${baseURL}/user/export`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error('Export failed');
  return res.blob();
}

/**
 * Permanently delete the authenticated user's account.
 */
export async function deleteAccount(): Promise<{ message: string }> {
  const res = await fetch(`${baseURL}/user`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error('Account deletion failed');
  return res.json();
}
