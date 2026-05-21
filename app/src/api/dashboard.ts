import { api } from './client';
import type { AccountType } from './accounts';

export type DashboardSummary = {
  period: { month: string };
  summary: {
    net_flow: number;
    monthly_income: number;
    monthly_expenses: number;
    upcoming_bills_total: number;
    upcoming_bills_count: number;
    total_balance?: number;
    account_count?: number;
    selected_account_count?: number;
  };
  selected_account_ids?: number[];
  accounts?: Array<{
    id: number;
    name: string;
    account_type: AccountType;
    institution: string | null;
    last_four: string | null;
    currency: string;
    opening_balance: number;
    balance: number;
    monthly_income: number;
    monthly_expenses: number;
    monthly_net_flow: number;
  }>;
  account_breakdown?: Array<{
    id: number;
    name: string;
    account_type: AccountType;
    institution: string | null;
    last_four: string | null;
    currency: string;
    opening_balance: number;
    balance: number;
    monthly_income: number;
    monthly_expenses: number;
    monthly_net_flow: number;
  }>;
  recent_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
    type: 'INCOME' | 'EXPENSE' | string;
    category_id: number | null;
    account_id?: number | null;
    account_name?: string | null;
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

export async function getDashboardSummary(
  month?: string,
  accountIds?: number[],
): Promise<DashboardSummary> {
  const qs = new URLSearchParams();
  if (month) qs.set('month', month);
  if (accountIds && accountIds.length > 0) qs.set('account_ids', accountIds.join(','));
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return api<DashboardSummary>(`/dashboard/summary${query}`);
}
