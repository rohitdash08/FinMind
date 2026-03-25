import { api } from './client';

export type WeeklyDigest = {
  id: number;
  week_start: string;
  week_end: string;
  summary: string;
  tips: string[];
  highlights: string[];
  method: string;
  created_at: string;
};

export async function getLatestDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/latest');
}

export async function getDigestHistory(limit = 10): Promise<WeeklyDigest[]> {
  return api<WeeklyDigest[]>(`/digest/history?limit=${limit}`);
}

export async function generateDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/generate', { method: 'POST' });
}
