import { api } from './client';

export type ExportFormat = 'json' | 'csv';

export interface EncryptedExport {
  algorithm: string;
  kdf: string;
  iterations: number;
  salt: string;
  nonce: string;
  ciphertext: string;
  format: ExportFormat;
}

export async function exportData(
  password: string,
  format: ExportFormat,
): Promise<EncryptedExport> {
  return api<EncryptedExport>('/export', {
    method: 'POST',
    body: { password, format },
  });
}
