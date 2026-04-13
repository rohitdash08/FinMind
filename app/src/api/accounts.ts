import { api } from './client';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: string;
  currency: string;
  balance: number;
  institution: string | null;
  active: boolean;
  created_at: string;
};

export type AccountOverview = {
  total_accounts: number;
  total_balance: number;
  net_worth: number;
  assets: number;
  liabilities: number;
  by_type: Record<string, { count: number; total_balance: number }>;
  accounts: FinancialAccount[];
};

export async function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function createAccount(data: {
  name: string;
  account_type: string;
  balance?: number;
  currency?: string;
  institution?: string;
}): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: data });
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export async function updateAccount(
  id: number,
  data: Partial<{ name: string; balance: number; institution: string; active: boolean; account_type: string }>,
): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: data });
}

export async function deleteAccount(id: number): Promise<void> {
  return api<void>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
