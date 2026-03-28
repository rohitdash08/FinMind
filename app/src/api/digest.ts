import { api } from './client';

export type WeeklyDigest = {
  period: {
    week_start: string;
    week_end: string;
  };
  summary: {
    total_income: number;
    total_expenses: number;
    net_flow: number;
    transaction_count: number;
  };
  comparison: {
    prev_week_expenses: number;
    prev_week_income: number;
    week_over_week_change_pct: number;
  };
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  daily_spending: Array<{
    date: string;
    amount: number;
  }>;
  top_transactions: Array<{
    id: number;
    amount: number;
    description: string;
    date: string;
    category_id: number | null;
  }>;
  insights: string[];
};

export type DigestWeek = {
  week_start: string;
  week_end: string;
};

export async function getWeeklyDigest(weekStart?: string): Promise<WeeklyDigest> {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : '';
  return api<WeeklyDigest>(`/digest${query}`);
}

export async function getAvailableWeeks(count?: number): Promise<DigestWeek[]> {
  const query = count ? `?count=${encodeURIComponent(count)}` : '';
  return api<DigestWeek[]>(`/digest/weeks${query}`);
}
