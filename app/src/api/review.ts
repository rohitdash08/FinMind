import { api } from './client';

export type MonthlyReview = {
  period: string;
  previous_period: string;
  current: MonthAggregate;
  previous: MonthAggregate;
  reviews: ReviewItem[];
  recommendations: Recommendation[];
};

export type MonthAggregate = {
  total_income: number;
  total_expenses: number;
  net_flow: number;
  transaction_count: number;
  categories: CategoryBreakdown[];
  bills_total: number;
};

export type CategoryBreakdown = {
  name: string;
  amount: number;
};

export type ReviewItem = {
  type: string;
  severity: 'info' | 'medium' | 'high';
  title: string;
  description: string;
  change_pct?: number;
  category?: string;
  amount?: number;
  savings_rate?: number;
  bills_ratio?: number;
};

export type Recommendation = {
  action: string;
  priority: 'low' | 'medium' | 'high';
  message: string;
  category?: string;
  trend?: string;
};

export async function getMonthlyReview(month?: string): Promise<MonthlyReview> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<MonthlyReview>(`/review/monthly-review${query}`);
}
