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

export type WeeklySmartDigest = {
  period: string;
  total_spend: number;
  prev_total_spend: number;
  total_change_pct: number;
  significant_changes: Array<{
    category: string;
    current: number;
    previous: number;
    change_pct: number;
  }>;
  insights: string[];
  prediction: string;
  trend_analysis?: string;
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

export async function getWeeklySmartDigest(date?: string): Promise<WeeklySmartDigest> {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  return api<WeeklySmartDigest>(`/insights/weekly-digest${query}`);
}
