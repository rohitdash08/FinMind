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
  total_income: number;
  total_expenses: number;
  net_flow: number;
  average_daily_expense: number;
  previous_week: {
    week_start: string;
    week_end: string;
    total_income: number;
    total_expenses: number;
    net_flow: number;
  };
  trend: {
    income_change_pct: number;
    expense_change_pct: number;
    net_flow_change: number;
  };
  daily_totals: Array<{
    date: string;
    income: number;
    expenses: number;
    net_flow: number;
  }>;
  top_categories: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
  }>;
  insights: string[];
  recommended_actions: string[];
  method: 'heuristic' | string;
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
  weekStart?: string;
}): Promise<WeeklyDigest> {
  const query = params?.weekStart ? `?week_start=${encodeURIComponent(params.weekStart)}` : '';
  return api<WeeklyDigest>(`/insights/weekly-digest${query}`);
}
