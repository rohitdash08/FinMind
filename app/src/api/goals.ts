import { api } from './client';

export type GoalStatus = 'ACTIVE' | 'COMPLETED' | 'PAUSED';

export interface GoalMilestone {
  pct: number;
  amount: number;
  reached: boolean;
}

export interface SavingsGoal {
  id: number;
  title: string;
  description: string | null;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  status: GoalStatus;
  monthly_target: number | null;
  icon: string | null;
  progress_pct: number;
  milestones: GoalMilestone[];
  days_remaining: number | null;
  created_at: string;
  updated_at: string;
}

export interface GoalCreate {
  title: string;
  description?: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string;
  monthly_target?: number;
  icon?: string;
}

export type GoalUpdate = Partial<GoalCreate & { status: GoalStatus }>;

export async function listGoals(status?: GoalStatus): Promise<SavingsGoal[]> {
  const qs = status ? `?status=${status}` : '';
  return api<SavingsGoal[]>(`/goals${qs}`);
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`);
}

export async function createGoal(payload: GoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/goals', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: GoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function depositToGoal(id: number, amount: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}/deposit`, { method: 'POST', body: { amount } });
}

export async function deleteGoal(id: number): Promise<void> {
  return api<void>(`/goals/${id}`, { method: 'DELETE' });
}
