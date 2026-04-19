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
  summary?: string;
  highlighted_trend?: string;
  action_items?: string[];
  score?: number;
  suggested_total?: number;
  breakdown?: {
    needs: number;
    wants: number;
    savings: number;
  };
  tips?: string[];
  analytics: {
    week_over_week_change_pct: number;
    current_week_expenses: number;
    previous_week_expenses: number;
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

export async function getWeeklyDigest(params?: {
  weekStart?: string;
  weekEnd?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklyDigest> {
  const queryParts = [];
  if (params?.weekStart) queryParts.push(`week_start=${encodeURIComponent(params.weekStart)}`);
  if (params?.weekEnd) queryParts.push(`week_end=${encodeURIComponent(params.weekEnd)}`);
  
  const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  const headers: Record<string, string> = {};
  
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  
  return api<WeeklyDigest>(`/insights/weekly-digest${query}`, { headers });
}

