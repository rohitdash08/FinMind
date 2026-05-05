import { api } from './client';

export type WeeklyBreakdown = {
  week_start: string;
  week_end: string;
  total: number;
  txn_count: number;
  categories: Array<{
    category: string;
    amount: number;
    count: number;
  }>;
  wow_delta: number | null;
  wow_delta_pct: number | null;
  trend: 'up' | 'down' | 'flat';
};

export type WeeklyDigest = {
  period: {
    weeks: number;
    from: string | null;
    to: string | null;
  };
  summary: {
    total_spending: number;
    total_transactions: number;
    average_weekly: number;
  };
  weekly_breakdown: WeeklyBreakdown[];
  top_categories: Array<{
    category: string;
    total: number;
  }>;
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    due_date: string | null;
    cadence: string;
  }>;
};

export async function getWeeklyDigest(weeks?: number): Promise<WeeklyDigest> {
  const query = weeks ? `?weeks=${weeks}` : '';
  return api<WeeklyDigest>(`/digest/weekly${query}`);
}
