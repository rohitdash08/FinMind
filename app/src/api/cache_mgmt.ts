import { api } from './client';

export type CacheStats = {
  total_keys: number;
  hits: number;
  misses: number;
  hit_rate: number;
};

export type CacheInvalidateResponse = {
  deleted: number;
};

export type CacheKeysResponse = {
  keys: string[];
};

export async function getCacheStats(): Promise<CacheStats> {
  return api<CacheStats>('/cache/stats');
}

export async function invalidateCache(keys?: string[]): Promise<CacheInvalidateResponse> {
  return api<CacheInvalidateResponse>('/cache/invalidate', {
    method: 'POST',
    body: keys && keys.length > 0 ? { keys } : {},
  });
}

export async function listCacheKeys(): Promise<CacheKeysResponse> {
  return api<CacheKeysResponse>('/cache/keys');
}
