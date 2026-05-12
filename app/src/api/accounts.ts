import { api } from './client';

export type AccountType =
  | 'CHECKING'
  | 'SAVINGS'
  | 'CREDIT_CARD'
  | 'INVESTMENT'
  | 'LOAN'
  | 'CASH'
  | 'OTHER';

export type FinancialAccount = {
  id: number;
  name: string;
  account_type: AccountType | string;
  balance: number;
  currency: string;
  institution: string | null;
  active: boolean;
  monthly_income?: number;
  monthly_expenses?: number;
  monthly_net_flow?: number;
  transaction_count?: number;
};

export type AccountsOverview = {
  period: { month: string };
  summary: {
    account_count: number;
    assets: number;
    liabilities: number;
    net_worth: number;
  };
  accounts: FinancialAccount[];
  by_type: Array<{ account_type: string; count: number; balance: number }>;
  by_currency: Array<{
    currency: string;
    assets: number;
    liabilities: number;
    net_worth: number;
  }>;
  recent_transactions: Array<{
    id: number;
    account_id: number;
    account_name: string;
    description: string;
    amount: number;
    currency: string;
    date: string;
    type: 'INCOME' | 'EXPENSE' | string;
  }>;
};

export type NewAccount = {
  name: string;
  account_type: AccountType;
  balance: number;
  currency: string;
  institution?: string;
};

export async function getAccountsOverview(month?: string): Promise<AccountsOverview> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return api<AccountsOverview>(`/accounts/overview${query}`);
}

export async function createAccount(payload: NewAccount): Promise<FinancialAccount> {
  return api<FinancialAccount>('/accounts', {
    method: 'POST',
    body: payload,
  });
}
