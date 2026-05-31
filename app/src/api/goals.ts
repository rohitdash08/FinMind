import { api } from './client';

export type Goal = {
  id: number;
  title: string;
  description: string | null;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  icon: string | null;
  active: boolean;
  created_at: string | null;
};

export type GoalCreate = {
  title: string;
  description?: string | null;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string | null;
  icon?: string | null;
};

export type GoalUpdate = Partial<GoalCreate> & {
  active?: boolean;
};

export type GoalMilestone = {
  id: number;
  goal_id: number;
  label: string;
  target_amount: number;
  reached: boolean;
  reached_at: string | null;
  created_at: string | null;
};

export type GoalMilestoneCreate = {
  label: string;
  target_amount: number;
};

export async function listGoals(): Promise<Goal[]> {
  return api<Goal[]>('/goals');
}

export async function createGoal(payload: GoalCreate): Promise<{ id: number }> {
  return api<{ id: number }>('/goals', { method: 'POST', body: payload });
}

export async function updateGoal(id: number, payload: GoalUpdate): Promise<{ message: string }> {
  return api<{ message: string }>(`/goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteGoal(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/goals/${id}`, { method: 'DELETE' });
}

export async function contributeToGoal(id: number, amount: number): Promise<{ current_amount: number }> {
  return api<{ current_amount: number }>(`/goals/${id}/contribute`, { method: 'POST', body: { amount } });
}

export async function listMilestones(goalId: number): Promise<GoalMilestone[]> {
  return api<GoalMilestone[]>(`/goals/${goalId}/milestones`);
}

export async function createMilestone(goalId: number, payload: GoalMilestoneCreate): Promise<{ id: number }> {
  return api<{ id: number }>(`/goals/${goalId}/milestones`, { method: 'POST', body: payload });
}

export async function deleteMilestone(goalId: number, milestoneId: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/goals/${goalId}/milestones/${milestoneId}`, { method: 'DELETE' });
}
