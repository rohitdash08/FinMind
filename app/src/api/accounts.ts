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
  institution: string | null;
  balance: number;
  currency: string;
  is_active: boolean;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AccountCreate = {
  name: string;
  account_type?: AccountType;
  institution?: string;
  balance?: number;
  currency?: string;
  notes?: string;
};

export type AccountUpdate = Partial<AccountCreate> & {
  is_active?: boolean;
};

export type AccountWithStats = FinancialAccount & {
  monthly_income: number;
  monthly_expenses: number;
  monthly_net: number;
  transaction_count: number;
};

export type AccountsOverview = {
  period: { month: string };
  net_worth: number;
  total_assets: number;
  total_liabilities: number;
  aggregate: {
    monthly_income: number;
    monthly_expenses: number;
    monthly_net: number;
  };
  accounts: AccountWithStats[];
  account_count: number;
  recent_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
    type: 'INCOME' | 'EXPENSE' | string;
    currency: string;
    account_id: number | null;
  }>;
};

export type AccountTransaction = {
  id: number;
  description: string;
  amount: number;
  date: string;
  type: string;
  currency: string;
  category_id: number | null;
  account_id: number | null;
};

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listAccounts(includeInactive = false): Promise<FinancialAccount[]> {
  const qs = includeInactive ? '?include_inactive=true' : '';
  return api<FinancialAccount[]>(`/accounts${qs}`);
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export async function createAccount(payload: AccountCreate): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: payload });
}

export async function updateAccount(
  id: number,
  payload: AccountUpdate,
): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Overview & transactions
// ---------------------------------------------------------------------------

export async function getAccountsOverview(month?: string): Promise<AccountsOverview> {
  const qs = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<AccountsOverview>(`/accounts/overview${qs}`);
}

export async function getAccountTransactions(
  accountId: number,
  params?: { page?: number; page_size?: number },
): Promise<AccountTransaction[]> {
  const qs = new URLSearchParams();
  if (params?.page) qs.set('page', String(params.page));
  if (params?.page_size) qs.set('page_size', String(params.page_size));
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return api<AccountTransaction[]>(`/accounts/${accountId}/transactions${query}`);
}
