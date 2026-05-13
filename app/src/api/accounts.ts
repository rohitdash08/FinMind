import { api } from './client';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: string;
  currency: string;
  opening_balance: number;
  active: boolean;
};

export async function listAccounts(): Promise<FinancialAccount[]> {
  return api<FinancialAccount[]>('/accounts');
}

export async function createAccount(payload: {
  name: string;
  account_type?: string;
  currency?: string;
  opening_balance?: number;
}): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', {
    method: 'POST',
    body: payload,
  });
}
