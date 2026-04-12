import { api } from './client';

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  percentage: number;
};

export type WeeklyDigest = {
  week: string;
  start_date: string;
  end_date: string;
  total_spent: number;
  category_breakdown: CategoryBreakdown[];
  week_over_week_change: number;
  previous_week_total: number;
  trends: string[];
  insights: string[];
  transaction_count: number;
};

export async function getWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const query = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigest>(`/digest/weekly${query}`);
}
