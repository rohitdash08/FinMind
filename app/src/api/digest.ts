import { api } from './client';

export type WeeklyDigest = {
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  wow_income_change_pct: number | null;
  wow_expense_change_pct: number | null;
  category_breakdown: Array<{
    category: string;
    amount: number;
    percentage: number;
  }>;
  daily_breakdown: Array<{
    day: string;
    amount: number;
  }>;
  transaction_count: number;
  insights: string[];
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
};

export async function getWeeklyDigest(params?: {
  week?: string;
  currency?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyDigest> {
  const queryParts: string[] = [];
  if (params?.week) queryParts.push(`week=${encodeURIComponent(params.week)}`);
  if (params?.currency) queryParts.push(`currency=${encodeURIComponent(params.currency)}`);
  const query = queryParts.length ? `?${queryParts.join('&')}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklyDigest>(`/digest/weekly${query}`, { headers });
}
