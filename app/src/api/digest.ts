import { api } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DigestSummary = {
  total_income: number;
  total_expenses: number;
  net_savings: number;
  transaction_count: number;
};

export type WeekOverWeek = {
  income_change: number | null;
  expense_change: number | null;
  savings_change: number | null;
  prev_total_expenses: number;
  prev_total_income: number;
};

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  transaction_count: number;
  share_pct: number;
};

export type DailySpending = {
  date: string;
  day_name: string;
  amount: number;
};

export type Trend = {
  metric: string;
  direction: 'UP' | 'DOWN' | 'FLAT' | 'NEW' | 'GONE';
  change_pct: number | null;
  description: string;
};

export type UpcomingBill = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  due_date: string;
  cadence: string;
  autopay: boolean;
};

export type Insight = {
  type: 'positive' | 'neutral' | 'warning';
  title: string;
  message: string;
};

export type WeeklyDigest = {
  week: string;
  period: { start: string; end: string };
  summary: DigestSummary;
  week_over_week: WeekOverWeek;
  category_breakdown: CategoryBreakdown[];
  daily_spending: DailySpending[];
  trends: Trend[];
  upcoming_bills: UpcomingBill[];
  insights: Insight[];
  currency?: string;
};

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

export async function getWeeklyDigest(params?: {
  week?: string;
  currency?: string;
}): Promise<WeeklyDigest> {
  const searchParams = new URLSearchParams();
  if (params?.week) searchParams.set('week', params.week);
  if (params?.currency) searchParams.set('currency', params.currency);
  const qs = searchParams.toString();
  return api<WeeklyDigest>(`/digest/weekly${qs ? `?${qs}` : ''}`);
}
