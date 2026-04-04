import { api } from './client';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: 'checking' | 'savings' | 'credit';
  balance: number;
  last_transaction: string | null;
};

export const getAccounts = () => api<FinancialAccount[]>('/accounts');

export const createAccount = (data: { name: string; account_type: string; balance: number }) =>
  api<FinancialAccount>('/accounts', { method: 'POST', body: data });
