import { api } from './client';

export type SavingsMilestone = {
  id: number;
  percent: number;
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
  progress: number;
  active: boolean;
  created_at: string;
  milestones: SavingsMilestone[];
};

export type SavingsGoalCreate = {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string | null;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export async function listSavingsGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings/goals');
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`);
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings/goals', { method: 'POST', body: payload });
}

export async function updateSavingsGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api(`/savings/goals/${id}`, { method: 'DELETE' });
}

export async function contributeSavingsGoal(id: number, amount: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings/goals/${id}/contribute`, {
    method: 'POST',
    body: { amount },
  });
}
