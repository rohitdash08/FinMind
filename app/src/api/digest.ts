import { api } from './client';

export type WeeklyDigest = {
  total_spent: number;
  last_week_total: number;
  pct_change: number;
  top_categories: Array<{ name: string; amount: number }>;
  biggest_expense: { description: string; amount: number; date: string } | null;
  savings_rate: number;
  insight: string;
  week_start: string;
  week_end: string;
};

export async function getWeeklyDigest(): Promise<WeeklyDigest> {
  return api<WeeklyDigest>('/digest/weekly');
}
