import { api } from './client';

export type Budget = {
  id: number;
  category_id: number;
  amount: number;
  period: 'MONTHLY' | 'WEEKLY';
};

export type BudgetWarning = {
  budget_id: number;
  category_id: number;
  category_name: string;
  budget_amount: number;
  spent: number;
  percentage: number;
  period: string;
  level: 'warning' | 'exceeded';
};

export async function listBudgets(): Promise<Budget[]> {
  return api<Budget[]>('/budgets');
}

export async function createBudget(data: {
  category_id: number;
  amount: number;
  period: string;
}): Promise<Budget> {
  return api<Budget>('/budgets', { method: 'POST', body: data });
}

export async function updateBudget(
  id: number,
  data: { amount?: number; period?: string },
): Promise<Budget> {
  return api<Budget>(`/budgets/${id}`, { method: 'PATCH', body: data });
}

export async function deleteBudget(id: number): Promise<void> {
  await api(`/budgets/${id}`, { method: 'DELETE' });
}

export async function getBudgetWarnings(): Promise<BudgetWarning[]> {
  return api<BudgetWarning[]>('/budgets/warnings');
}
