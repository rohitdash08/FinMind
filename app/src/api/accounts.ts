import { api } from './client';

export type AccountType = 'CHECKING' | 'SAVINGS' | 'CREDIT_CARD' | 'INVESTMENT' | 'CASH' | 'OTHER';

export type Account = {
  id: number;
  name: string;
  type: AccountType;
  balance: number;
  currency: string;
  institution?: string;
  account_number_last4?: string;
  color?: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountCreate = {
  name: string;
  type: AccountType;
  balance?: number;
  currency?: string;
  institution?: string;
  account_number_last4?: string;
  color?: string;
};

export type AccountUpdate = Partial<AccountCreate> & {
  active?: boolean;
};

export type AccountSummary = {
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  accounts_by_type: Record<AccountType, { count: number; total: number }>;
  currency: string;
};

export type AccountTransaction = {
  id: number;
  account_id: number;
  amount: number;
  type: 'DEPOSIT' | 'WITHDRAWAL' | 'TRANSFER';
  description?: string;
  date: string;
  balance_after: number;
};

/**
 * List all accounts for the current user
 */
export async function listAccounts(params?: {
  type?: AccountType;
  active?: boolean;
}): Promise<Account[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = '/accounts' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<Account[]>(path);
}

/**
 * Get a single account by ID
 */
export async function getAccount(id: number): Promise<Account> {
  return api<Account>(`/accounts/${id}`);
}

/**
 * Create a new account
 */
export async function createAccount(payload: AccountCreate): Promise<Account> {
  return api<Account>('/accounts', { method: 'POST', body: payload });
}

/**
 * Update an existing account
 */
export async function updateAccount(id: number, payload: AccountUpdate): Promise<Account> {
  return api<Account>(`/accounts/${id}`, { method: 'PATCH', body: payload });
}

/**
 * Delete an account
 */
export async function deleteAccount(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/accounts/${id}`, { method: 'DELETE' });
}

/**
 * Get overall account summary and net worth
 */
export async function getAccountSummary(): Promise<AccountSummary> {
  return api<AccountSummary>('/accounts/summary');
}

/**
 * Record a deposit to an account
 */
export async function depositToAccount(
  id: number,
  amount: number,
  description?: string,
): Promise<Account> {
  return api<Account>(`/accounts/${id}/deposit`, {
    method: 'POST',
    body: { amount, description },
  });
}

/**
 * Record a withdrawal from an account
 */
export async function withdrawFromAccount(
  id: number,
  amount: number,
  description?: string,
): Promise<Account> {
  return api<Account>(`/accounts/${id}/withdraw`, {
    method: 'POST',
    body: { amount, description },
  });
}

/**
 * Transfer funds between accounts
 */
export async function transferBetweenAccounts(
  fromAccountId: number,
  toAccountId: number,
  amount: number,
  description?: string,
): Promise<{ from_account: Account; to_account: Account }> {
  return api(`/accounts/transfer`, {
    method: 'POST',
    body: {
      from_account_id: fromAccountId,
      to_account_id: toAccountId,
      amount,
      description,
    },
  });
}

/**
 * Get transaction history for an account
 */
export async function getAccountTransactions(
  accountId: number,
  params?: {
    from?: string;
    to?: string;
    limit?: number;
  },
): Promise<AccountTransaction[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = `/accounts/${accountId}/transactions` + (qs.toString() ? `?${qs.toString()}` : '');
  return api<AccountTransaction[]>(path);
}
