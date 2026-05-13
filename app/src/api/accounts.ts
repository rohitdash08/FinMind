import { api } from './client';

export interface Account {
  id: number;
  name: string;
  account_type: string;
  balance: number;
  currency: string;
}

export interface ConsolidatedView {
  total_balance: number;
  account_count: number;
  by_type: Record<string, number>;
  accounts: Account[];
}

export async function listAccounts(): Promise<Account[]> {
  const res = await api<{ accounts: Account[] }>('/accounts');
  return res.accounts;
}

export async function createAccount(data: {
  name: string;
  account_type?: string;
  balance?: number;
  currency?: string;
}): Promise<{ id: number }> {
  return api('/accounts', { method: 'POST', body: data });
}

export async function getConsolidatedView(): Promise<ConsolidatedView> {
  return api<ConsolidatedView>('/accounts/consolidated');
}

export async function deleteAccount(id: number): Promise<void> {
  await api(`/accounts/${id}`, { method: 'DELETE' });
}
