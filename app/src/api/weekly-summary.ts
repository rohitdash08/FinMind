import { api } from './client';

export type WeekComparison = {
  current_week: number;
  previous_week: number;
  change_pct: number;
};

export type CategorySpend = {
  category_id: number | null;
  category_name: string;
  amount: number;
  percentage: number;
};

export type TopExpense = {
  id: number;
  amount: number;
  description: string;
  date: string;
  category_name: string;
};

export type WeeklySummary = {
  week_start: string;
  week_end: string;
  total_spent: number;
  total_income: number;
  net_flow: number;
  comparison: WeekComparison;
  category_breakdown: CategorySpend[];
  top_expenses: TopExpense[];
  insights: string[];
};

export async function getWeeklySummary(weekOf?: string): Promise<WeeklySummary> {
  const query = weekOf ? `?week_of=${encodeURIComponent(weekOf)}` : '';
  return api<WeeklySummary>(`/weekly-summary${query}`);
}
