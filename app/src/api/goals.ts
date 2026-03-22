import { api } from './client';

export interface SavingsMilestone {
  id: number;
  goal_id: number;
  percentage: number;
  threshold_amount: number;
  reached: boolean;
  reached_at: string | null;
}

export interface SavingsGoal {
  id: number;
  name: string;
  description: string;
  icon: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  progress_pct: number;
  is_completed: boolean;
  deadline: string | null;
  created_at: string;
  updated_at: string | null;
  milestones: SavingsMilestone[];
}

export interface SavingsGoalCreate {
  name: string;
  target_amount: number;
  description?: string;
  icon?: string;
  currency?: string;
  current_amount?: number;
  deadline?: string | null;
}

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/goals');
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`);
}

export async function createGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/goals', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function depositToGoal(id: number, amount: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}/deposit`, { method: 'POST', body: { amount } });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/goals/${id}`, { method: 'DELETE' });
}
