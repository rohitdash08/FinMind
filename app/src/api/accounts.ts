import { api } from './client';

export type AccountType = 'BANK' | 'CREDIT' | 'CASH' | 'INVESTMENT' | 'WALLET' | 'OTHER';

export interface Account {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  initial_balance: number;
  color: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AccountWithStats extends Account {
  income: number;
  expenses: number;
  balance: number;
}

export interface OverviewSummary {
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  unassigned_income: number;
  unassigned_expenses: number;
  account_count: number;
}

export interface AccountOverview {
  accounts: AccountWithStats[];
  summary: OverviewSummary;
}

export function listAccounts(): Promise<Account[]> {
  return api<Account[]>('/accounts');
}

export function getAccount(id: number): Promise<Account> {
  return api<Account>(`/accounts/${id}`);
}

export function createAccount(payload: {
  name: string;
  account_type: AccountType;
  currency?: string;
  initial_balance?: number;
  color?: string;
}): Promise<Account> {
  return api<Account>('/accounts', { method: 'POST', body: payload });
}

export function updateAccount(
  id: number,
  payload: Partial<{
    name: string;
    account_type: AccountType;
    currency: string;
    initial_balance: number;
    color: string;
  }>,
): Promise<Account> {
  return api<Account>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export function deleteAccount(id: number): Promise<void> {
  return api<void>(`/accounts/${id}`, { method: 'DELETE' });
}

export function getOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
