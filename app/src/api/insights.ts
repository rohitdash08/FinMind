import { api } from './client';

export type ConfidenceScore = {
  score: number;
  label: 'no_data' | 'low' | 'medium' | 'high' | 'very_high';
  months_analyzed: number;
};

export type CategorySuggestion = {
  category_id: number | null;
  category_name: string;
  suggested_limit: number;
  average_spending: number;
  trend_pct: number;
  trend_direction: 'increasing' | 'decreasing' | 'stable';
  months_with_data: number;
  monthly_history: Record<string, number>;
};

export type SpendingTrend = {
  direction: 'increasing' | 'decreasing' | 'stable';
  change_pct: number;
};

export type DataRange = {
  months_requested: number;
  months_with_data: number;
  oldest_month?: string;
  newest_month?: string;
};

export type BudgetSuggestion = {
  month: string;
  suggested_total: number;
  breakdown: {
    needs: number;
    wants: number;
    savings: number;
  };
  confidence?: ConfidenceScore;
  spending_trend?: SpendingTrend;
  category_suggestions?: CategorySuggestion[];
  data_range?: DataRange;
  monthly_totals?: Record<string, number>;
  tips?: string[];
  analytics?: {
    month_over_month_change_pct: number;
    current_month_expenses: number;
    previous_month_expenses: number;
    top_categories: Array<{ category_id: string; amount: number }>;
  };
  persona?: string;
  method: 'gemini' | 'heuristic' | 'heuristic_default' | 'openai' | string;
  warnings?: string[];
  net_flow?: number;
};

export async function getBudgetSuggestion(params?: {
  month?: string;
  months?: number;
  geminiApiKey?: string;
  persona?: string;
}): Promise<BudgetSuggestion> {
  const searchParams = new URLSearchParams();
  if (params?.month) searchParams.set('month', params.month);
  if (params?.months) searchParams.set('months', String(params.months));
  const query = searchParams.toString();
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<BudgetSuggestion>(
    `/insights/budget-suggestion${query ? `?${query}` : ''}`,
    { headers },
  );
}
