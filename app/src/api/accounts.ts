import { apiClient } from './client';

export type AccountType = 'checking' | 'savings' | 'credit_card' | 'investment' | 'cash' | 'loan' | 'other';

export interface FinancialAccount {
  id: string;
  name: string;
  type: AccountType;
  balance: number;
  currency: string;
  institution: string;
  color: string;
  lastSyncedAt: string;
  isPrimary: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateAccountRequest {
  name: string;
  type: AccountType;
  balance: number;
  currency?: string;
  institution: string;
  color?: string;
  isPrimary?: boolean;
}

export interface UpdateAccountRequest {
  name?: string;
  type?: AccountType;
  balance?: number;
  currency?: string;
  institution?: string;
  color?: string;
  isPrimary?: boolean;
}

export interface AccountsSummary {
  totalBalance: number;
  totalAssets: number;
  totalLiabilities: number;
  accountCount: number;
  byType: Record<AccountType, { count: number; total: number }>;
}

export const getAccounts = async (): Promise<FinancialAccount[]> => {
  const response = await apiClient.get('/accounts');
  return response.data;
};

export const getAccount = async (id: string): Promise<FinancialAccount> => {
  const response = await apiClient.get(`/accounts/${id}`);
  return response.data;
};

export const createAccount = async (data: CreateAccountRequest): Promise<FinancialAccount> => {
  const response = await apiClient.post('/accounts', data);
  return response.data;
};

export const updateAccount = async (id: string, data: UpdateAccountRequest): Promise<FinancialAccount> => {
  const response = await apiClient.put(`/accounts/${id}`, data);
  return response.data;
};

export const deleteAccount = async (id: string): Promise<void> => {
  await apiClient.delete(`/accounts/${id}`);
};

export const getAccountsSummary = async (): Promise<AccountsSummary> => {
  const response = await apiClient.get('/accounts/summary');
  return response.data;
};
