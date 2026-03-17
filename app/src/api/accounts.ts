import { api } from './client';

export type AccountType = 'BANK' | 'CREDIT' | 'CASH' | 'INVESTMENT' | 'WALLET' | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  initial_balance: number;
  current_balance: number;
  color: string | null;
  active: boolean;
  created_at: string;
};

export type AccountSummary = FinancialAccount & {
  total_income: number;
  total_spent: number;
};

export type RecentTransaction = {
  id: number;
  account_id: number;
  amount: number;
  currency: string;
  expense_type: string;
  notes: string | null;
  spent_at: string | null;
};

export type AccountsOverview = {
  total_balance: number;
  total_income: number;
  total_spent: number;
  net_flow: number;
  top_spending_account: string | null;
  accounts: AccountSummary[];
  recent_transactions: RecentTransaction[];
};

export type CreateAccountPayload = {
  name: string;
  account_type?: AccountType;
  currency?: string;
  initial_balance?: number;
  color?: string;
};

export type UpdateAccountPayload = Partial<CreateAccountPayload>;

export async function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function getAccountsOverview(): Promise<AccountsOverview> {
  return api<AccountsOverview>('/accounts/overview');
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`);
}

export async function createAccount(payload: CreateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateAccount(id: number, payload: UpdateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteAccount(id: number): Promise<void> {
  await api<void>(`/accounts/${id}`, { method: 'DELETE' });
}
