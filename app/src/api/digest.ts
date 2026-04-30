import { api } from './client';

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  share_pct: number;
};

export type DigestTrends = {
  expense_change_pct: number;
  income_change_pct: number;
  previous_week_expenses: number;
  previous_week_income: number;
  expense_trend: 'up' | 'down' | 'flat';
  income_trend: 'up' | 'down' | 'flat';
};

export type WeeklyDigest = {
  id: number;
  user_id: number;
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  top_categories: CategoryBreakdown[];
  trends: DigestTrends;
  ai_insights: string;
  created_at: string | null;
};

export async function getWeeklyDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/weekly');
}

export async function getWeeklyDigestByDate(dateStr: string): Promise<WeeklyDigest> {
  return api<WeeklyDigest>(`/digest/weekly/${encodeURIComponent(dateStr)}`);
}

export async function getDigestHistory(limit?: number): Promise<WeeklyDigest[]> {
  const query = limit ? `?limit=${limit}` : '';
  return api<WeeklyDigest[]>(`/digest/history${query}`);
}

export async function forceGenerateDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/generate', { method: 'POST' });
}
