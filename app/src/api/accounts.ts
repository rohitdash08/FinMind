import { api } from './client';

export type AccountType = 'BANK' | 'CREDIT_CARD' | 'INVESTMENT' | 'CASH' | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  type: AccountType;
  currency: string;
  balance: number | null;
  created_at: string;
};

export async function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function createAccount(data: {
  name: string;
  type?: AccountType;
  currency?: string;
  balance?: number | null;
}): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', { method: 'POST', body: data });
}

export async function updateAccount(
  id: number,
  data: Partial<{
    name: string;
    type: AccountType;
    currency: string;
    balance: number | null;
  }>
): Promise<FinancialAccount> {
  return api<FinancialAccount>(`/accounts/${id}`, { method: 'PATCH', body: data });
}

export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api(`/accounts/${id}`, { method: 'DELETE' });
}