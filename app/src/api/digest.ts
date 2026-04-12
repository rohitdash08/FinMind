import { api } from './client';

export type WeeklyDigest = {
  week: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  tips?: string[];
  summary?: string;
  analytics: {
    week_over_week_change_pct: number;
    current_week_expenses: number;
    previous_week_expenses: number;
    top_categories: Array<{ category_id: string; amount: number }>;
  };
  persona?: string;
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
};

export async function getWeeklyDigest(params?: {
  week?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyDigest> {
  const weekQuery = params?.week ? `?week=${encodeURIComponent(params.week)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklyDigest>(`/digest/weekly${weekQuery}`, { headers });
}
