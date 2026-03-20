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

export type SavingsOpportunityTrend = Record<string, number | string>;

export type SavingsOpportunity = {
  type: string;
  title: string;
  description: string;
  potential_savings: number;
  category: string | null;
  trend: SavingsOpportunityTrend;
};

export type SavingsOpportunitiesResponse = {
  month: string;
  opportunities: SavingsOpportunity[];
};

export async function getSavingsOpportunities(
  params?: { month?: string },
): Promise<SavingsOpportunitiesResponse> {
  const monthQuery = params?.month
    ? `?month=${encodeURIComponent(params.month)}`
    : '';
  return api<SavingsOpportunitiesResponse>(
    `/insights/savings-opportunities${monthQuery}`,
  );
}
