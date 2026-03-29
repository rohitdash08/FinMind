import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT_CARD' | 'INVESTMENT' | 'LOAN' | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  institution: string | null;
  balance: number;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountCreate = {
  name: string;
  account_type: AccountType;
  institution?: string;
  balance?: number;
  currency?: string;
  is_active?: boolean;
};

export type AccountUpdate = Partial<AccountCreate>;

export type AccountsByType = {
  type: AccountType;
  count: number;
  total_balance: number;
  accounts: FinancialAccount[];
};

export type AccountOverview = {
  total_accounts: number;
  total_balance: number;
  by_type: AccountsByType[];
  by_currency: { currency: string; balance: number }[];
  by_institution: { institution: string; count: number; total_balance: number }[];
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

export async function updateAccount(id: number, payload: AccountUpdate): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getAccountsOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
