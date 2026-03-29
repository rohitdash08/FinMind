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

export type WeeklySummary = {
  week: string;
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  net_flow: number;
  insights: string[];
  tips: string[];
  analytics: {
    week_start: string;
    week_end: string;
    current_week_expenses: number;
    previous_week_expenses: number;
    week_over_week_change_pct: number;
    top_categories: Array<{ category_id: string; amount: number }>;
    unusual_spend: Array<{
      category_id: string;
      current_amount: number;
      previous_amount: number;
      increase_pct: number;
    }>;
  };
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
};

export async function getWeeklySummary(params?: {
  week?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklySummary> {
  const weekQuery = params?.week ? `?week=${encodeURIComponent(params.week)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklySummary>(`/insights/weekly-summary${weekQuery}`, { headers });
}
