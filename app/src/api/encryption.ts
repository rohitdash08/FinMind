import { api } from './client';

export type KeyMetadata = {
  key_id: string;
  algorithm: string;
  created_at: string;
};

export type VerifyResult = {
  valid: boolean;
};

export async function storeKey(payload: { key_id: string; algorithm: string }): Promise<KeyMetadata> {
  return api<KeyMetadata>('/encryption/keys', { method: 'POST', body: payload });
}

export async function listKeys(): Promise<KeyMetadata[]> {
  return api<KeyMetadata[]>('/encryption/keys');
}

export async function verifyHash(payload: { data_hash: string; expected_hash: string }): Promise<VerifyResult> {
  return api<VerifyResult>('/encryption/verify', { method: 'POST', body: payload });
}
