import { api } from './client';

export type SavingsGoal = {
  id: number;
  title: string;
  target_amount: number;
  current_amount: number;
  deadline: string; // ISO date
  monthly_target: number;
  status: 'on-track' | 'ahead' | 'behind' | 'completed';
  created_at: string;
  updated_at: string;
};

export type SavingsGoalCreate = {
  title: string;
  target_amount: number;
  deadline: string; // ISO date
  current_amount?: number;
};

export type SavingsGoalUpdate = Partial<SavingsGoalCreate> & {
  status?: 'on-track' | 'ahead' | 'behind' | 'completed';
};

export type SavingsContribution = {
  id: number;
  goal_id: number;
  amount: number;
  date: string;
  note?: string;
  created_at: string;
};

export type SavingsContributionCreate = {
  goal_id: number;
  amount: number;
  date: string;
  note?: string;
};

export type SavingsMilestone = {
  id: number;
  goal_id: number;
  title: string;
  target_amount: number;
  achieved: boolean;
  achieved_at?: string;
  created_at: string;
};

export type SavingsMilestoneCreate = {
  goal_id: number;
  title: string;
  target_amount: number;
};

export type SavingsMilestoneUpdate = {
  achieved?: boolean;
};

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
  return api<{ message: string }>(`/savings/goals/${id}`, { method: 'DELETE' });
}

export async function addSavingsContribution(payload: SavingsContributionCreate): Promise<SavingsContribution> {
  return api<SavingsContribution>('/savings/contributions', { method: 'POST', body: payload });
}

export async function listSavingsContributions(goalId: number): Promise<SavingsContribution[]> {
  return api<SavingsContribution[]>(`/savings/goals/${goalId}/contributions`);
}

export async function listSavingsMilestones(goalId: number): Promise<SavingsMilestone[]> {
  return api<SavingsMilestone[]>(`/savings/goals/${goalId}/milestones`);
}

export async function createSavingsMilestone(payload: SavingsMilestoneCreate): Promise<SavingsMilestone> {
  return api<SavingsMilestone>('/savings/milestones', { method: 'POST', body: payload });
}

export async function updateSavingsMilestone(id: number, payload: SavingsMilestoneUpdate): Promise<SavingsMilestone> {
  return api<SavingsMilestone>(`/savings/milestones/${id}`, { method: 'PATCH', body: payload });
}

export async function deleteSavingsMilestone(id: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/savings/milestones/${id}`, { method: 'DELETE' });
}
