import { api } from './client';

export type SavingsMilestone = {
  id: number;
  goal_id: number;
  name: string;
  amount: number;
  reached: boolean;
  reached_at: string | null;
};

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  target_date: string | null;
  status: 'ACTIVE' | 'COMPLETED';
  progress_pct: number;
  remaining_amount: number;
  milestones: SavingsMilestone[];
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  target_date?: string;
  milestones?: Array<{ name: string; amount: number }>;
};

export async function listSavingsGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings-goals');
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings-goals', { method: 'POST', body: payload });
}

export async function updateSavingsGoal(
  id: number,
  payload: Partial<SavingsGoalCreate>,
): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsGoal(id: number): Promise<{ message?: string }> {
  return api<{ message?: string }>(`/savings-goals/${id}`, { method: 'DELETE' });
}
