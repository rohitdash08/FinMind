import { api } from './client';

export type BackupCreateResponse = {
  checksum: string;
  size: number;
  created_at: string;
};

export type BackupMeta = {
  checksum: string;
  created_at: string;
  size: number;
};

export type BackupVerifyResponse = {
  checksum: string;
  valid: boolean;
};

export async function createBackup(): Promise<BackupCreateResponse> {
  return api<BackupCreateResponse>('/backup/create', { method: 'POST' });
}

export async function listBackups(): Promise<BackupMeta[]> {
  return api<BackupMeta[]>('/backup/list');
}

export async function verifyBackup(checksum: string): Promise<BackupVerifyResponse> {
  return api<BackupVerifyResponse>(`/backup/verify/${encodeURIComponent(checksum)}`);
}
