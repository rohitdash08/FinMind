import { api } from './client';

export type Account = {
  id: number;
  name: string;
  account_type: string;
  currency: string;
  initial_balance: number;
  is_default: boolean;
  active: boolean;
  created_at: string | null;
};

export type AccountCreate = {
  name: string;
  account_type?: string;
  currency?: string;
  initial_balance?: number;
  is_default?: boolean;
};

export type AccountUpdate = Partial<AccountCreate>;

export type AccountSummary = {
  account: Account;
  balance: number;
  total_income: number;
  total_expenses: number;
  monthly_spend: number;
  recent_transactions: {
    id: number;
    description: string;
    amount: number;
    date: string;
    type: string;
    category_id: number | null;
    currency: string;
  }[];
};

export type AccountOverview = {
  total_net_worth: number;
  accounts: {
    account: Account;
    balance: number;
    total_income: number;
    total_expenses: number;
    monthly_spend: number;
  }[];
};

export async function listAccounts(): Promise<Account[]> {
  return api<Account[]>('/accounts');
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

export async function getAccountSummary(id: number): Promise<AccountSummary> {
  return api<AccountSummary>(`/accounts/${id}/summary`);
}

export async function getAccountsOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}
