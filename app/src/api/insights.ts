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

export type WeeklySummary = {
  period: {
    week_start: string;
    week_end: string;
    previous_week_start: string;
    previous_week_end: string;
  };
  summary: {
    income: number;
    expenses: number;
    net_flow: number;
    transaction_count: number;
    income_transaction_count: number;
    expense_transaction_count: number;
    savings_rate_pct: number;
  };
  comparison: {
    previous_income: number;
    previous_expenses: number;
    previous_net_flow: number;
    income_change_pct: number;
    expense_change_pct: number;
    net_flow_change: number;
  };
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    transaction_count: number;
    share_pct: number;
  }>;
  daily_breakdown: Array<{
    date: string;
    income: number;
    expenses: number;
    net_flow: number;
    transaction_count: number;
  }>;
  largest_expenses: Array<{
    id: number;
    description: string;
    amount: number;
    currency: string;
    date: string;
    category_id: number | null;
    category_name: string;
  }>;
  highlights: string[];
  insights: Array<{
    type: string;
    severity: string;
    title: string;
    detail: string;
  }>;
  recommendations: string[];
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

export async function getWeeklySummary(params?: {
  weekStart?: string;
}): Promise<WeeklySummary> {
  const query = params?.weekStart
    ? `?week_start=${encodeURIComponent(params.weekStart)}`
    : '';
  return api<WeeklySummary>(`/insights/weekly-summary${query}`);
}
