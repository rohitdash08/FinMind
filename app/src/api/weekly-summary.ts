import { api } from './client';

export type WeeklyTotals = {
  income: number;
  expenses: number;
  net: number;
  transaction_count: number;
};

export type DailyBreakdown = {
  date: string;
  income: number;
  expenses: number;
};

export type CategoryBreakdown = {
  category_id: number | null;
  category_name: string;
  amount: number;
  count: number;
  share_pct: number;
};

export type TopExpense = {
  id: number;
  description: string;
  amount: number;
  date: string;
  category_id: number | null;
  currency: string;
};

export type UpcomingBill = {
  id: number;
  name: string;
  amount: number;
  currency: string;
  next_due_date: string;
  cadence: string;
};

export type WeeklyTrends = {
  expense_change_pct: number | null;
  income_change_pct: number | null;
  previous_week_expenses: number;
  previous_week_income: number;
};

export type WeeklySummary = {
  week: { start: string; end: string };
  totals: WeeklyTotals;
  daily_breakdown: DailyBreakdown[];
  category_breakdown: CategoryBreakdown[];
  top_expenses: TopExpense[];
  upcoming_bills: UpcomingBill[];
  trends: WeeklyTrends;
};

export async function getWeeklySummary(weekOf?: string): Promise<WeeklySummary> {
  const query = weekOf ? `?week_of=${encodeURIComponent(weekOf)}` : '';
  return api<WeeklySummary>(`/weekly-summary${query}`);
}
