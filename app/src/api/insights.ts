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

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  count: number;
  share_pct: number;
};

export type DailySpending = {
  date: string;
  amount: number;
};

export type WeeklyDigest = {
  period: {
    week_start: string;
    week_end: string;
    prev_week_start: string;
    prev_week_end: string;
  };
  summary: {
    total_expenses: number;
    total_income: number;
    net_flow: number;
    prev_week_expenses: number;
    prev_week_income: number;
    wow_change_pct: number;
    trend: 'up' | 'down' | 'stable';
    transaction_count: number;
  };
  category_breakdown: CategoryBreakdown[];
  top_categories: CategoryBreakdown[];
  daily_spending: DailySpending[];
  upcoming_bills: {
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
  }[];
  insights: string[];
};

export async function getWeeklyDigest(refDate?: string): Promise<WeeklyDigest> {
  const qs = refDate ? `?date=${refDate}` : '';
  return api<WeeklyDigest>(`/insights/weekly-digest${qs}`);
}

export async function sendWeeklyDigestEmail(refDate?: string): Promise<{ sent: boolean }> {
  const qs = refDate ? `?date=${refDate}` : '';
  return api<{ sent: boolean }>(`/insights/weekly-digest/send${qs}`, { method: 'POST' });
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
