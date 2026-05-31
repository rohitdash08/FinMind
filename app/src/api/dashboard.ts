import { api } from './client';

export type DashboardSummary = {
  period: { month: string };
  summary: {
    net_flow: number;
    monthly_income: number;
    monthly_expenses: number;
    upcoming_bills_total: number;
    upcoming_bills_count: number;
  };
  recent_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
    type: 'INCOME' | 'EXPENSE' | string;
    category_id: number | null;
    currency: string;
  }>;
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
    cadence: string;
    channel_email: boolean;
    channel_whatsapp: boolean;
  }>;
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  errors?: string[];
};

export async function getDashboardSummary(month?: string): Promise<DashboardSummary> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<DashboardSummary>(`/dashboard/summary${query}`);
}
