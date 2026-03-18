import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────

export type CategorySpending = {
  category_id: number | null;
  category_name: string;
  amount: number;
  transaction_count: number;
  share_pct: number;
};

export type DailySpending = {
  date: string;
  amount: number;
};

export type SpendingSpike = {
  category_name: string;
  current_amount: number;
  previous_amount: number;
  increase_pct: number | null;
};

export type BillItem = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  next_due_date: string;
  cadence: string;
  autopay_enabled?: boolean;
  days_until_due?: number;
  days_overdue?: number;
};

export type WeeklyDigest = {
  period: {
    start: string;
    end: string;
    week_offset: number;
  };
  summary: {
    total_spent: number;
    previous_week_spent: number;
    wow_change_pct: number | null;
    total_income: number;
    net_flow: number;
    transaction_count: number;
    daily_average: number;
  };
  categories: CategorySpending[];
  previous_categories: CategorySpending[];
  daily_spending: DailySpending[];
  spikes: SpendingSpike[];
  savings_opportunities: string[];
  bills: {
    upcoming: BillItem[];
    overdue: BillItem[];
    upcoming_total: number;
    overdue_total: number;
  };
  narrative: string;
  narrative_method: 'ai' | 'heuristic';
};

export type WeeklyTotal = {
  week_start: string;
  week_end: string;
  total_spent: number;
  total_income: number;
  net_flow: number;
};

export type CategoryTrend = {
  category_name: string;
  trend: 'increasing' | 'decreasing' | 'stable';
  data: Array<{ week_start: string; amount: number }>;
  total: number;
  average: number;
};

export type SpendingTrends = {
  weeks_included: number;
  weekly_totals: WeeklyTotal[];
  category_trends: CategoryTrend[];
};

// ── API Functions ────────────────────────────────────────────────────

export async function getWeeklyDigest(params?: {
  weekOffset?: number;
  geminiApiKey?: string;
}): Promise<WeeklyDigest> {
  const qs = new URLSearchParams();
  if (params?.weekOffset !== undefined) {
    qs.set('week_offset', String(params.weekOffset));
  }
  const query = qs.toString() ? `?${qs.toString()}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  return api<WeeklyDigest>(`/digest/weekly${query}`, { headers });
}

export async function getSpendingTrends(params?: {
  weeks?: number;
}): Promise<SpendingTrends> {
  const qs = new URLSearchParams();
  if (params?.weeks !== undefined) {
    qs.set('weeks', String(params.weeks));
  }
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return api<SpendingTrends>(`/digest/trends${query}`);
}
