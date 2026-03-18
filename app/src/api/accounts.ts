import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT' | 'INVESTMENT' | 'CASH' | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  balance: number;
  institution: string | null;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountOverview = {
  period: { month: string };
  net_worth: number;
  accounts: Array<{
    id: number;
    name: string;
    account_type: AccountType;
    balance: number;
    institution: string | null;
    currency: string;
  }>;
  account_summary_by_type: Array<{
    account_type: AccountType;
    total_balance: number;
  }>;
  recent_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
    type: string;
    category_id: number | null;
    currency: string;
  }>;
  spending_breakdown: Array<{
    category_id: number | null;
    category_name: string;
    amount: number;
    share_pct: number;
  }>;
  errors?: string[];
};

export type CreateAccountPayload = {
  name: string;
  account_type: AccountType;
  balance: number;
  institution?: string;
  currency?: string;
};

export type UpdateAccountPayload = Partial<CreateAccountPayload & { is_active: boolean }>;

export async function listAccounts(includeInactive = false): Promise<FinancialAccount[]> {
  const q = includeInactive ? '?include_inactive=true' : '';
  return api<FinancialAccount[]>(`/accounts${q}`);
}

export async function createAccount(payload: CreateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateAccount(id: number, payload: UpdateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deleteAccount(id: number): Promise<void> {
  await api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getAccountOverview(month?: string): Promise<AccountOverview> {
  const q = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<AccountOverview>(`/dashboard/overview${q}`);
}

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  CHECKING: 'Checking',
  SAVINGS: 'Savings',
  CREDIT: 'Credit Card',
  INVESTMENT: 'Investment',
  CASH: 'Cash',
  OTHER: 'Other',
};
