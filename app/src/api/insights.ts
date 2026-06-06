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
  currency?: string | null;
  summary: {
    income: number;
    expenses: number;
    net_flow: number;
    transaction_count: number;
    category_breakdown: Array<{ category: string; amount: number }>;
    daily_breakdown: Array<{ date: string; amount: number }>;
    top_expenses: Array<{
      id: number;
      date: string;
      description: string;
      amount: number;
      category: string;
    }>;
  };
  previous_week: {
    week_start: string;
    week_end: string;
    income: number;
    expenses: number;
    net_flow: number;
  };
  week_over_week_change_pct: number;
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    due_date: string;
    autopay_enabled: boolean;
  }>;
  insights: string[];
  recommendations: string[];
  method: string;
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
  week?: string;
  currency?: string;
}): Promise<WeeklyDigest> {
  const query = new URLSearchParams();
  if (params?.week) query.set('week', params.week);
  if (params?.currency) query.set('currency', params.currency);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return api<WeeklyDigest>(`/insights/weekly-digest${suffix}`);
}
