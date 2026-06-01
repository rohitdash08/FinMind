import { api } from './client';

export type SavingsGoal = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null; // ISO date
  category: string;
  priority: 'low' | 'medium' | 'high';
  status: 'active' | 'completed' | 'paused';
  milestones: Milestone[];
  created_at: string;
  updated_at: string;
};

export type Milestone = {
  id: number;
  goal_id: number;
  title: string;
  target_amount: number;
  reached: boolean;
  reached_at: string | null;
};

export type GoalCreate = {
  name: string;
  target_amount: number;
  deadline?: string | null;
  category?: string;
  priority?: 'low' | 'medium' | 'high';
};

export type GoalUpdate = Partial<Omit<GoalCreate, 'target_amount'>> & {
  target_amount?: number;
  status?: 'active' | 'completed' | 'paused';
};

export type GoalDeposit = {
  amount: number;
  note?: string;
};

export async function listGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/goals');
}

export async function getGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`);
}

export async function createGoal(data: GoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/goals', { method: 'POST', body: data });
}

export async function updateGoal(id: number, data: GoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}`, { method: 'PATCH', body: data });
}

export async function deleteGoal(id: number): Promise<void> {
  return api<void>(`/goals/${id}`, { method: 'DELETE' });
}

export async function depositToGoal(id: number, data: GoalDeposit): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/goals/${id}/deposit`, { method: 'POST', body: data });
}

export async function getGoalSummary(): Promise<{
  total_saved: number;
  total_target: number;
  active_goals: number;
  completed_goals: number;
  upcoming_milestones: Milestone[];
}> {
  return api('/goals/summary');
}
