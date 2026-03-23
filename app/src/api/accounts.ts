import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT_CARD' | 'CASH' | 'INVESTMENT' | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  balance: number;
  currency: string;
  institution: string | null;
  active: boolean;
  created_at: string | null;
};

export type AccountCreate = {
  name: string;
  account_type?: AccountType;
  balance?: number;
  currency?: string;
  institution?: string;
};

export type AccountUpdate = Partial<AccountCreate> & {
  active?: boolean;
};

export type AccountsOverview = {
  accounts: FinancialAccount[];
  total_balance: number;
  totals_by_currency: Record<string, number>;
  account_count: number;
  recent_expenses: {
    id: number;
    amount: number;
    currency: string;
    description: string;
    date: string;
  }[];
  upcoming_bills: {
    id: number;
    name: string;
    amount: number;
    currency: string;
    next_due_date: string;
  }[];
};

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

export async function getAccountsOverview(): Promise<AccountsOverview> {
  return api<AccountsOverview>('/accounts/overview');
}
