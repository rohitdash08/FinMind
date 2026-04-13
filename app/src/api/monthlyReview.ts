import { api } from './client';

export type MonthlyReview = {
  month: string;
  income: number;
  expenses: number;
  savings_rate: number;
  top_categories: Array<{
    category: string;
    amount: number;
  }>;
  vs_previous_month: {
    income_change: number;
    expense_change: number;
  };
  highlights: string[];
};

export async function getMonthlyReview(month?: string): Promise<MonthlyReview> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<MonthlyReview>(`/review/monthly${query}`);
}
