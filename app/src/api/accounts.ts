import { api } from './client';

export type AccountType = 'CURRENT' | 'SAVINGS' | 'CREDIT' | 'INVESTMENT';

export type Account = {
  id: number;
  user_id: number;
  name: string;
  type: AccountType;
  balance: number;
  currency: string;
  is_default: boolean;
  created_at: string;
};

export type AccountCreate = {
  name: string;
  type: AccountType;
  balance?: number;
  currency?: string;
  is_default?: boolean;
};

export type AccountsOverview = {
  total_balance: number;
  currency: string;
  accounts_count: number;
  allocation: Array<{
    type: AccountType;
    balance: number;
    share_pct: number;
  }>;
};

export async function getAccounts(): Promise<Account[]> {
  return api<Account[]>('/accounts');
}

export async function createAccount(payload: AccountCreate): Promise<Account> {
  return api<Account>('/accounts', { method: 'POST', body: payload });
}

export async function getAccountsOverview(): Promise<AccountsOverview> {
  return api<AccountsOverview>('/accounts/overview');
}
