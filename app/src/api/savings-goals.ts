import { api } from './client';

export type SavingsGoal = {
  id: number;
  title: string;
  target_amount: number;
  current_amount: number;
  currency: string;
  deadline: string | null;
  status: 'ON_TRACK' | 'BEHIND' | 'AHEAD' | 'COMPLETED';
  monthly_target: number | null;
  created_at: string;
};

export type SavingsGoalCreate = {
  title: string;
  target_amount: number;
  current_amount?: number;
  currency?: string;
  deadline?: string;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate>;

export type Milestone = {
  id: number;
  goal_id: number;
  title: string;
  amount: number;
  reached_at: string | null;
  created_at: string;
};

export type MilestoneCreate = {
  title: string;
  amount: number;
};

export async function listSavingsGoals(): Promise<SavingsGoal[]> {
  return api<SavingsGoal[]>('/savings-goals');
}

export async function createSavingsGoal(payload: SavingsGoalCreate): Promise<SavingsGoal> {
  return api<SavingsGoal>('/savings-goals', { method: 'POST', body: payload });
}

export async function getSavingsGoal(id: number): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`);
}

export async function updateSavingsGoal(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
  return api<SavingsGoal>(`/savings-goals/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsGoal(id: number): Promise<{ message: string }> {
  return api(`/savings-goals/${id}`, { method: 'DELETE' });
}

export async function listMilestones(goalId: number): Promise<Milestone[]> {
  return api<Milestone[]>(`/savings-goals/${goalId}/milestones`);
}

export async function createMilestone(goalId: number, payload: MilestoneCreate): Promise<Milestone> {
  return api<Milestone>(`/savings-goals/${goalId}/milestones`, { method: 'POST', body: payload });
}

export async function deleteMilestone(goalId: number, milestoneId: number): Promise<{ message: string }> {
  return api(`/savings-goals/${goalId}/milestones/${milestoneId}`, { method: 'DELETE' });
}
