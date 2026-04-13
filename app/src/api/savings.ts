import { api } from './client';

export type Milestone = {
  id: number;
  label: string;
  percentage: number;
  target_amount: number;
  reached: boolean;
  reached_at: string | null;
};

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  active: boolean;
  progress: number;
  created_at: string;
  milestones: Milestone[];
};

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings/goals');
}

export async function createGoal(data: {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string;
}): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings/goals', { method: 'POST', body: data });
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`);
}

export async function updateGoal(
  id: number,
  data: Partial<{ name: string; current_amount: number; target_amount: number; deadline: string | null; active: boolean }>,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`, { method: 'PATCH', body: data });
}

export async function deleteGoal(id: number): Promise<void> {
  return api<void>(`/savings/goals/${id}`, { method: 'DELETE' });
}
