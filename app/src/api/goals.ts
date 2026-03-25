import { api } from './client';

export type GoalStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  status: GoalStatus;
  created_at: string;
};

export type GoalCreate = {
  name: string;
  target_amount: number;
  currency?: string;
  deadline?: string;
};

export type Contribution = {
  id: number;
  goal_id: number;
  amount: number;
  note: string | null;
  contributed_at: string;
};

export type GoalProgress = {
  goal_id: number;
  name: string;
  target: number;
  current: number;
  remaining: number;
  progress_pct: number;
  status: GoalStatus;
  on_track: boolean;
  deadline?: string;
  days_left?: number;
  daily_savings_needed?: number;
  milestones: { pct: number; reached: boolean; amount: number }[];
};

export async function listGoals(status?: GoalStatus): Promise<SavingsGoal[]> {
  const qs = status ? `?status=${status}` : '';
  return api<SavingsGoal[]>(`/goals${qs}`);
}

export async function createGoal(payload: GoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/goals', { method: 'POST', body: payload });
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`);
}

export async function updateGoal(id: number, payload: Partial<GoalCreate>): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function cancelGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'DELETE' });
}

export async function getProgress(id: number): Promise<GoalProgress> {
  return api<GoalProgress>(`/goals/${id}/progress`);
}

export async function addContribution(id: number, amount: number, note?: string): Promise<Contribution> {
  return api<Contribution>(`/goals/${id}/contribute`, { method: 'POST', body: { amount, note } });
}

export async function listContributions(id: number): Promise<Contribution[]> {
  return api<Contribution[]>(`/goals/${id}/contributions`);
}
