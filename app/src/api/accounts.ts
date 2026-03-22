import { api } from './client';

export type FinancialAccount = {
  id: number;
  name: string;
  type: 'CHECKING' | 'SAVINGS' | 'CREDIT_CARD' | 'INVESTMENT' | 'LOAN' | 'CASH';
  balance: number;
  currency: string;
  institution: string;
  last_synced: string | null;
  is_active: boolean;
  created_at: string;
};

export type AccountSummary = {
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  currency: string;
  accounts: FinancialAccount[];
};

export type CreateAccountPayload = {
  name: string;
  type: FinancialAccount['type'];
  balance: number;
  currency?: string;
  institution?: string;
};

export type UpdateAccountPayload = Partial<CreateAccountPayload> & {
  is_active?: boolean;
};

export async function getAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function getAccountSummary(): Promise<AccountSummary> {
  return api<AccountSummary>('/accounts/summary');
}

export async function getAccount(id: number): Promise<FinancialAccount> {
  return api<FinancialAccount>("/accounts/${id}");
}

export async function createAccount(payload: CreateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: payload });
}

export async function updateAccount(id: number, payload: UpdateAccountPayload): Promise<FinancialAccount> {
  return api<FinancialAccount>("/accounts/${id}", { method: 'PATCH', body: payload });
}

export async function deleteAccount(id: number): Promise<void> {
  return api<void>("/accounts/${id}", { method: 'DELETE' });
}