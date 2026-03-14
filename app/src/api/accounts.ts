import { api } from './client';

export type AccountType = 'BANK' | 'CREDIT' | 'INVESTMENT' | 'CASH';

export type Account = {
  id: number;
  name: string;
  account_type: AccountType;
  institution: string | null;
  balance: number;
  currency: string;
  color: string;
  active: boolean;
  created_at: string | null;
};

export type AccountCreate = {
  name: string;
  account_type?: AccountType;
  institution?: string;
  balance?: number;
  currency?: string;
  color?: string;
};

export type AccountUpdate = Partial<AccountCreate> & { active?: boolean };

export type TypeBreakdown = {
  type: AccountType;
  total: number;
  count: number;
  accounts: Account[];
};

export type AccountsOverview = {
  total_balance: number;
  net_worth: number;
  total_assets: number;
  total_liabilities: number;
  account_count: number;
  type_breakdown: TypeBreakdown[];
};

export async function listAccounts(params?: {
  include_inactive?: boolean;
}): Promise<Account[]> {
  const qs = new URLSearchParams();
  if (params?.include_inactive) qs.set('include_inactive', 'true');
  const path = '/accounts' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<Account[]>(path);
}

export async function getAccount(id: number): Promise<Account> {
  return api<Account>(`/accounts/${id}`);
}

export async function createAccount(payload: AccountCreate): Promise<Account> {
  return api<Account>('/accounts', { method: 'POST', body: payload });
}

export async function updateAccount(id: number, payload: AccountUpdate): Promise<Account> {
  return api<Account>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getAccountsOverview(): Promise<AccountsOverview> {
  return api<AccountsOverview>('/accounts/overview');
}
