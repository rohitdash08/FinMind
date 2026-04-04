import { api } from './client';

export type BudgetLimit = {
  id: number;
  category_id: number | null;
  monthly_limit: number;
  month: string;
};

export type BudgetWithSpend = BudgetLimit & {
  category_name: string;
  spent: number;
};

export type BudgetWarning = {
  category_id: number | null;
  category_name: string;
  monthly_limit: number;
  spent: number;
  remaining: number;
  pct_used: number;
  status: 'ok' | 'warning' | 'critical' | 'over';
};

export async function getBudgets(month: string): Promise<BudgetWithSpend[]> {
  return api<BudgetWithSpend[]>(`/budgets?month=${encodeURIComponent(month)}`);
}

export async function setBudget(data: {
  category_id: number | null;
  monthly_limit: number;
  month: string;
}): Promise<BudgetLimit> {
  return api<BudgetLimit>('/budgets', { method: 'POST', body: data });
}

export async function deleteBudget(id: number): Promise<{ message: string }> {
  return api(`/budgets/${id}`, { method: 'DELETE' });
}

export async function getBudgetWarnings(month: string): Promise<BudgetWarning[]> {
  return api<BudgetWarning[]>(`/budgets/warnings?month=${encodeURIComponent(month)}`);
}
