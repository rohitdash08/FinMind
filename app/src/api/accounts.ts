import { api } from './client';

export type AccountType =
  | 'CHECKING'
  | 'SAVINGS'
  | 'CREDIT_CARD'
  | 'INVESTMENT'
  | 'LOAN'
  | 'CASH'
  | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  balance: number;
  currency: string;
  institution: string | null;
  last_four: string | null;
  color: string | null;
  include_in_overview: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type MultiAccountOverview = {
  period: { month: string };
  accounts: FinancialAccount[];
  totals: {
    net_worth: number;
    total_assets: number;
    total_liabilities: number;
  };
  monthly_summary: {
    income: number;
    expenses: number;
    net_flow: number;
  };
  upcoming_bills: Array<{
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
    cadence: string;
  }>;
  category_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  errors?: string[];
};

export type CreateAccountPayload = {
  name: string;
  account_type?: AccountType;
  balance?: number;
  currency?: string;
  institution?: string;
  last_four?: string;
  color?: string;
  include_in_overview?: boolean;
};

export type UpdateAccountPayload = Partial<CreateAccountPayload>;

export async function listAccounts(includeInactive = false): Promise<FinancialAccount[]> {
  const q = includeInactive ? '?include_inactive=true' : '';
  return api<FinancialAccount[]>(`/accounts${q}`);
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export async function createAccount(payload: CreateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function updateAccount(
  id: number,
  payload: UpdateAccountPayload
): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getMultiAccountOverview(month?: string): Promise<MultiAccountOverview> {
  const q = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<MultiAccountOverview>(`/accounts/overview${q}`);
}
