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
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  totals: {
    income: number;
    expenses: number;
    net_flow: number;
    savings_rate_pct: number;
  };
  trends: {
    income_change_pct: number;
    expenses_change_pct: number;
    net_flow_change_pct: number;
  };
  top_categories: Array<{ category_id: string; amount: number; share_pct: number }>;
  daily: Array<{ date: string; income: number; expenses: number; net_flow: number }>;
  insights: string[];
  method: 'heuristic' | string;
};

export async function getWeeklySummary(endDate?: string): Promise<WeeklySummary> {
  const query = endDate ? `?end_date=${encodeURIComponent(endDate)}` : '';
  return api<WeeklySummary>(`/insights/weekly-summary${query}`);
}
