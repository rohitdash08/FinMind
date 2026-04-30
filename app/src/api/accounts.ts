import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT_CARD' | 'WALLET' | 'CASH' | 'OTHER';

export type Account = {
  id: number;
  user_id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  balance: number;
  icon: string | null;
  color: string | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type AccountCreate = {
  name: string;
  account_type?: AccountType;
  currency?: string;
  balance?: number;
  icon?: string;
  color?: string;
};

export type AccountUpdate = Partial<AccountCreate>;

export type AccountOverview = {
  total_balance: number;
  account_count: number;
  accounts: Array<
    Account & {
      recent_activity: Array<{
        id: number;
        description: string;
        amount: number;
        date: string;
        type: string;
      }>;
    }
  >;
};

export async function listAccounts(): Promise<Account[]> {
  return api<Account[]>('/accounts');
}

export async function getAccount(id: number): Promise<Account> {
  return api<Account>(`/accounts/${id}`);
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

export async function getAccountOverview(): Promise<AccountOverview> {
  return api<AccountOverview>('/accounts/overview');
}

export async function recalculateBalance(id: number): Promise<{ balance: number }> {
  return api<{ balance: number }>(`/accounts/${id}/recalculate`, { method: 'POST' });
}
