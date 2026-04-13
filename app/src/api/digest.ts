import { api } from './client';

export interface DigestInsight {
  type: 'warning' | 'positive' | 'info';
  title: string;
  message: string;
}

export interface CategoryBreakdown {
  category_id: number | null;
  category_name: string;
  amount: number;
  count: number;
  share_pct: number;
  wow_delta: number;
}

export interface DailySpending {
  date: string;
  day_name: string;
  amount: number;
}

export interface TopTransaction {
  id: number;
  description: string;
  amount: number;
  date: string;
  category_id: number | null;
}

export interface WeekOverWeek {
  expense_delta: number;
  expense_pct_change: number;
  income_delta: number;
  income_pct_change: number;
  previous_week_expenses: number;
  previous_week_income: number;
}

export interface WeeklyDigest {
  week: string;
  period: { start: string; end: string };
  summary: {
    total_income: number;
    total_expenses: number;
    net_flow: number;
    transaction_count: number;
  };
  category_breakdown: CategoryBreakdown[];
  week_over_week: WeekOverWeek;
  daily_spending: DailySpending[];
  top_transactions: TopTransaction[];
  insights: DigestInsight[];
  trends: {
    spending_direction: 'up' | 'down' | 'stable';
    income_direction: 'up' | 'down' | 'stable';
  };
}

export async function fetchWeeklyDigest(week?: string): Promise<WeeklyDigest> {
  const params = week ? `?week=${encodeURIComponent(week)}` : '';
  return api<WeeklyDigest>(`/digest/weekly${params}`);
}
