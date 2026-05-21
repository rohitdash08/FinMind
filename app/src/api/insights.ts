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
  currency: string;
  summary: {
    income: number;
    expenses: number;
    net_flow: number;
    transaction_count: number;
    average_daily_expense: number;
    savings_rate_pct: number;
  };
  comparison: {
    previous_expenses: number;
    expense_change: number;
    expense_change_pct: number;
    trend: 'up' | 'down' | 'flat' | string;
  };
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
    previous_amount: number;
    change_pct: number;
    transaction_count: number;
  }>;
  daily_breakdown: Array<{
    date: string;
    day: string;
    expenses: number;
  }>;
  largest_expenses: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
  }>;
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    due_date: string;
    autopay_enabled: boolean;
  }>;
  highlights: string[];
  insights: string[];
  recommendations: string[];
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
  currency?: string;
}): Promise<WeeklySummary> {
  const query = new URLSearchParams();
  if (params?.weekStart) query.set('week_start', params.weekStart);
  if (params?.currency) query.set('currency', params.currency);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return api<WeeklySummary>(`/insights/weekly-summary${suffix}`);
}
