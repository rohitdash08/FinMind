import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  saved_amount: number;
  target_date: string | null;
  progress_pct: number;
  milestones: number[];
};

export const getSavingsGoals = () => api<SavingsGoal[]>('/savings-goals');

export const createSavingsGoal = (data: { name: string; target_amount: number; target_date?: string }) =>
  api<SavingsGoal>('/savings-goals', { method: 'POST', body: data });

export const updateSavingsGoal = (id: number, data: Partial<{ name: string; target_amount: number; saved_amount: number; target_date: string | null }>) =>
  api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PUT' as any, body: data });

export const deleteSavingsGoal = (id: number) =>
  api<{ message: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
