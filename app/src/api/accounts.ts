import api from "./index";

export type AccountType =
  | "CHECKING"
  | "SAVINGS"
  | "CREDIT"
  | "CASH"
  | "INVESTMENT"
  | "OTHER";

export interface FinancialAccount {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  initial_balance: number;
  current_balance: number;
  color?: string;
  active: boolean;
  created_at: string;
}

export interface AccountDetail extends FinancialAccount {
  recent_transactions: {
    id: number;
    amount: number;
    expense_type: string;
    notes?: string;
    spent_at: string;
    category_id?: number;
  }[];
}

export interface AccountsOverview {
  accounts: FinancialAccount[];
  by_type: Record<string, { count: number; total_balance: number }>;
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  account_count: number;
}

export interface CreateAccountPayload {
  name: string;
  account_type?: AccountType;
  currency?: string;
  initial_balance?: number;
  color?: string;
}

export const getAccounts = (): Promise<FinancialAccount[]> =>
  api.get("/accounts").then((r) => r.data);

export const createAccount = (
  payload: CreateAccountPayload
): Promise<FinancialAccount> =>
  api.post("/accounts", payload).then((r) => r.data);

export const getAccount = (id: number): Promise<AccountDetail> =>
  api.get(`/accounts/${id}`).then((r) => r.data);

export const updateAccount = (
  id: number,
  payload: Partial<CreateAccountPayload>
): Promise<FinancialAccount> =>
  api.patch(`/accounts/${id}`, payload).then((r) => r.data);

export const deleteAccount = (id: number): Promise<void> =>
  api.delete(`/accounts/${id}`).then((r) => r.data);

export const getAccountsOverview = (): Promise<AccountsOverview> =>
  api.get("/accounts/overview").then((r) => r.data);
