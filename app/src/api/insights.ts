import { api } from './client';

export type WeeklySummary = {
  week_start: string;
  week_end: string;
  total_income: number;
  total_expenses: number;
  previous_week_expenses: number;
  expense_change_pct: number;
  net_flow: number;
  transaction_count: number;
  average_daily_expense: number;
  top_categories: Array<{ category_id: string; amount: number }>;
  trend_insights: string[];
};

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

export async function getWeeklySummary(params?: { weekStart?: string }): Promise<WeeklySummary> {
  const query = params?.weekStart ? `?week_start=${encodeURIComponent(params.weekStart)}` : '';
  return api<WeeklySummary>(`/insights/weekly-summary${query}`);
}

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
