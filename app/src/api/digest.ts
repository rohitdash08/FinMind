import { api } from './client';

export type DigestInsight = {
  type: 'success' | 'warning' | 'info';
  title: string;
  message: string;
};

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  share_pct: number;
};

export type DailyBreakdown = {
  date: string;
  day_name: string;
  expenses: number;
  income: number;
};

export type WeekTrend = {
  week_start: string;
  week_end: string;
  income: number;
  expenses: number;
  net: number;
};

export type WeeklyDigestSummary = {
  period: {
    week_start: string;
    week_end: string;
  };
  overview: {
    total_income: number;
    total_expenses: number;
    net_flow: number;
    savings_rate: number | null;
    transaction_count: number;
    avg_daily_spending: number;
  };
  comparison: {
    prev_week_income: number;
    prev_week_expenses: number;
    spending_change_pct: number | null;
    income_change_pct: number | null;
  };
  category_breakdown: CategoryBreakdown[];
  biggest_expense: {
    id: number;
    amount: number;
    description: string;
    date: string;
    category_id: number | null;
  } | null;
  daily_breakdown: DailyBreakdown[];
  trend: WeekTrend[];
  insights: DigestInsight[];
};

export type WeeklyDigestResponse = {
  id: number;
  week_start: string;
  week_end: string;
  generated_at: string | null;
  summary: WeeklyDigestSummary;
};

export type DigestHistoryItem = {
  id: number;
  week_start: string;
  week_end: string;
  generated_at: string | null;
  summary: WeeklyDigestSummary;
};

export async function getWeeklyDigest(week?: string): Promise<WeeklyDigestResponse> {
  const query = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigestResponse>(`/digest/weekly${query}`);
}

export async function getDigestHistory(limit?: number): Promise<DigestHistoryItem[]> {
  const query = limit ? `?limit=${limit}` : '';
  return api<DigestHistoryItem[]>(`/digest/history${query}`);
}
