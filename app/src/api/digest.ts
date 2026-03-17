import { api } from './client';

export type CategoryBreakdown = {
  category: string;
  total: number;
  previous_total: number;
  delta: number;
  delta_pct: number | null;
};

export type UpcomingBill = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  due_date: string;
};

export type WeeklySummary = {
  total_spent: number;
  total_income: number;
  net_flow: number;
  prev_week_spent: number;
  wow_change_pct: number | null;
};

export type WeeklyDigest = {
  week_start: string;
  week_end: string;
  summary: WeeklySummary;
  category_breakdown: CategoryBreakdown[];
  top_spending_category: string | null;
  upcoming_bills: UpcomingBill[];
  insights: string[];
};

export async function getWeeklyDigest(weekStart?: string): Promise<WeeklyDigest> {
  const qs = weekStart ? `?week_start=${weekStart}` : '';
  return api<WeeklyDigest>(`/digest/weekly${qs}`);
}
