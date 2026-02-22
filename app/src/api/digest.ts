import { api } from './client';

export type WeeklyDigest = {
  period: { start: string; end: string };
  totals: {
    income: number;
    expenses: number;
    net: number;
  };
  comparison: {
    previous_week_expenses: number;
    change: number;
    change_percent: number | null;
  };
  category_breakdown: Array<{
    category: string;
    total: number;
    count: number;
  }>;
  daily_spending: Array<{
    date: string;
    amount: number;
  }>;
  highlights: string[];
};

export async function fetchWeeklyDigest(date?: string): Promise<WeeklyDigest> {
  const params = date ? `?date=${date}` : '';
  return api<WeeklyDigest>(`/digest/weekly${params}`);
}
