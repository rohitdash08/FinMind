import { api } from './client';

export type BudgetSuggestion = {
  month: string;
  suggested_total: number;
  breakdown: {
    needs: number;
    wants: number;
    savings: number;
  };
  tips?: string[];
  analytics: {
    month_over_month_change_pct: number;
    current_month_expenses: number;
    previous_month_expenses: number;
    top_categories: Array<{ category_id: string; amount: number }>;
  };
  persona?: string;
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
  net_flow?: number;
};

export async function getBudgetSuggestion(params?: {
  month?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<BudgetSuggestion> {
  const monthQuery = params?.month ? `?month=${encodeURIComponent(params.month)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<BudgetSuggestion>(`/insights/budget-suggestion${monthQuery}`, { headers });
}

export type WeeklyDigest = {
  week_start: string;
  week_end: string;
  total_expenses: number;
  total_income: number;
  net_flow: number;
  week_over_week_change_pct: number;
  previous_week_expenses: number;
  top_categories: Array<{ category: string; amount: number }>;
  daily_breakdown: Array<{ date: string; amount: number }>;
  insights: string[];
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
  return api<WeeklyDigest>(`/insights/weekly-digest${weekQuery}`, { headers });
}
