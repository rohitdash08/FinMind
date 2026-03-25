import { api } from './client';

export type AccountType = 'checking' | 'savings' | 'credit' | 'cash' | 'investment';

export type Account = {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  balance: number;
  is_active: boolean;
  color: string | null;
  created_at: string;
};

export type AccountCreate = {
  name: string;
  account_type: AccountType;
  currency?: string;
  balance?: number;
  color?: string;
};

export type AccountOverview = {
  total_balance: number;
  net_worth: number;
  account_count: number;
  by_type: Record<string, { count: number; total: number }>;
  accounts: Account[];
};

export async function listAccounts(includeInactive = false): Promise<Account[]> {
  const qs = includeInactive ? '?include_inactive=true' : '';
  return api<Account[]>(`/accounts${qs}`);
}

export async function createAccount(payload: AccountCreate): Promise<Account> {
  return api<Account>('/accounts', { method: 'POST', body: payload });
}

export async function getAccount(id: number): Promise<Account> {
  return api<Account>(`/accounts/${id}`);
}

export async function updateAccount(id: number, payload: Partial<AccountCreate>): Promise<Account> {
  return api<Account>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api(`/accounts/${id}`, { method: 'DELETE' });
}

export async function getOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
