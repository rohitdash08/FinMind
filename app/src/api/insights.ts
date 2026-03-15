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

export type WeeklyDigest = {
  week_start: string;
  week_end: string;
  total_spent: number;
  total_income: number;
  net_flow: number;
  wow_change_pct: number;
  category_breakdown: Record<string, number>;
  daily_breakdown: Record<string, number>;
  insights: string[];
  method: 'gemini' | 'heuristic' | string;
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

export async function getWeeklyDigest(params?: {
  offset?: number;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyDigest> {
  const offsetQuery = params?.offset !== undefined ? `?offset=${params.offset}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklyDigest>(`/insights/weekly-digest${offsetQuery}`, { headers });
}
