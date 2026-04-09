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

export type WeeklyFinancialSummary = {
  year_week: string; // e.g., "2023-W01"
  total_expenses: number;
  total_income: number;
  net_flow: number;
  top_expenses_by_category: Array<{ category_id: string; amount: number }>;
  spending_trend: {
    last_week_expenses: number;
    change_pct: number;
    trend_description: string;
  };
  insights?: string[];
  recommendations?: string[];
  persona?: string;
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
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

export async function getWeeklyFinancialSummary(params?: {
  yearWeek?: string; // e.g., "2023-W01"
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyFinancialSummary> {
  const weekQuery = params?.yearWeek ? `?week=${encodeURIComponent(params.yearWeek)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklyFinancialSummary>(`/insights/weekly-summary${weekQuery}`, { headers });
}
