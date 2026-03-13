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
  week: string;
  period: {
    start: string;
    end: string;
  };
  total_spent: number;
  total_income: number;
  net_flow: number;
  week_over_week_change_pct: number;
  previous_week_spent: number;
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    wow_change_pct: number | null;
  }>;
  daily_breakdown: Array<{
    date: string;
    amount: number;
  }>;
  top_expenses: Array<{
    id: number;
    amount: number;
    notes: string;
    date: string;
    category_id: number | null;
  }>;
  insights: string[];
  transaction_count: number;
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

export async function getWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const query = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigest>(`/insights/weekly-digest${query}`);
}
