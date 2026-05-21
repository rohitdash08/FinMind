import { api } from './client';

export type AccountType =
  | 'CASH'
  | 'CHECKING'
  | 'SAVINGS'
  | 'CREDIT_CARD'
  | 'INVESTMENT'
  | 'LOAN'
  | 'WALLET'
  | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType;
  institution: string | null;
  last_four: string | null;
  currency: string;
  opening_balance: number;
  active: boolean;
  balance: number;
  income_total: number;
  expense_total: number;
  created_at: string;
  updated_at: string;
};

export type FinancialAccountCreate = {
  name: string;
  account_type?: AccountType;
  institution?: string | null;
  last_four?: string | null;
  currency?: string;
  opening_balance?: number;
};

export type FinancialAccountUpdate = Partial<FinancialAccountCreate> & {
  active?: boolean;
};

export async function listAccounts(includeArchived = false): Promise<FinancialAccount[]> {
  const query = includeArchived ? '?include_archived=true' : '';
  return api<FinancialAccount[]>(`/accounts${query}`);
}

export async function createAccount(payload: FinancialAccountCreate): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: payload });
}

export async function updateAccount(
  id: number,
  payload: FinancialAccountUpdate,
): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

export async function archiveAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}
