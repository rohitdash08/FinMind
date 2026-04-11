import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT' | 'INVESTMENT' | 'CASH';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  balance: number;
  currency: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountCreate = {
  name: string;
  account_type?: AccountType;
  balance?: number;
  currency?: string;
};

export type AccountUpdate = Partial<AccountCreate>;

export type AccountsOverviewSummary = {
  total_accounts: number;
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  by_type: Record<string, number>;
};

export type AccountsOverview = {
  accounts: FinancialAccount[];
  summary: AccountsOverviewSummary;
};

export async function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function createAccount(payload: AccountCreate): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: payload });
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export async function updateAccount(id: number, payload: AccountUpdate): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PUT', body: payload });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getAccountsOverview(): Promise<AccountsOverview> {
  return api<AccountsOverview>('/accounts/overview');
}
