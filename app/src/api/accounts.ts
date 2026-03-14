import { api } from './client';

// ── Types ────────────────────────────────────────────────────────────
export type AccountType = 'BANK' | 'CREDIT' | 'CASH' | 'INVESTMENT' | 'WALLET' | 'OTHER';

export interface FinancialAccount {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  balance: number;
  institution: string | null;
  last_four: string | null;
  color: string;
  active: boolean;
  created_at: string;
}

export interface AccountCreate {
  name: string;
  account_type?: AccountType;
  currency?: string;
  balance?: number;
  institution?: string;
  last_four?: string;
  color?: string;
}

export type AccountUpdate = Partial<AccountCreate>;

export interface AccountOverview {
  total_accounts: number;
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  by_type: Record<string, { count: number; total_balance: number }>;
  by_currency: Record<string, number>;
  accounts: FinancialAccount[];
  recent_transactions: Array<{
    id: number;
    amount: number;
    currency: string;
    notes: string | null;
    date: string;
  }>;
}

// ── API calls ─────────────────────────────────────────────────────────
export function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export function createAccount(data: AccountCreate): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: data });
}

export function updateAccount(id: number, data: AccountUpdate): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: data });
}

export function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

export function getAccountsOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
